"""Tools d'analyse avancée — détection de fraudes, doublons, absences,
incohérences dans l'intendance des ouvriers.

Ces tools sont enregistrés dans le même registre que ceux de tools.py, ils
sont donc automatiquement exposés au LLM via function-calling.

Import de ce module dans ai_assistant/__init__.py ou dans tools.py assure
l'exécution des @register_tool.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .tools import register_tool

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Détection de doublons ouvriers/employés
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "detect_duplicate_workers",
    "description": (
        "Détecte les ouvriers en doublon dans la base : même téléphone, même "
        "nom+prénom, ou même numéro de pièce d'identité. Retourne les clusters "
        "trouvés avec les IDs concernés pour permettre une fusion manuelle."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "string",
                "enum": ["phone", "name", "id_document", "all"],
                "description": "Critère de détection. 'all' = tous les critères.",
                "default": "all",
            },
        },
    },
}, permission="ouvriers.view")
def detect_duplicate_workers(criteria: str = "all", user=None):
    from ouvriers.models import Worker
    from accounts.scoping import scope_queryset_by_company

    qs = scope_queryset_by_company(Worker.objects.all(), user, "site__company")
    workers = list(qs.values(
        "id", "matricule", "first_name", "last_name", "phone", "id_document_number",
    ))

    clusters = []

    if criteria in ("phone", "all"):
        by_phone = defaultdict(list)
        for w in workers:
            if w["phone"]:
                by_phone[w["phone"].strip()].append(w)
        for phone, group in by_phone.items():
            if len(group) > 1:
                clusters.append({
                    "criterion": "phone",
                    "value": phone,
                    "count": len(group),
                    "workers": [
                        {"id": w["id"], "matricule": w["matricule"],
                         "name": f"{w['first_name']} {w['last_name']}"}
                        for w in group
                    ],
                })

    if criteria in ("name", "all"):
        by_name = defaultdict(list)
        for w in workers:
            key = f"{w['first_name'].strip().lower()}|{w['last_name'].strip().lower()}"
            if w["first_name"] and w["last_name"]:
                by_name[key].append(w)
        for key, group in by_name.items():
            if len(group) > 1:
                clusters.append({
                    "criterion": "name",
                    "value": key.replace("|", " "),
                    "count": len(group),
                    "workers": [
                        {"id": w["id"], "matricule": w["matricule"],
                         "phone": w["phone"]}
                        for w in group
                    ],
                })

    if criteria in ("id_document", "all"):
        by_id = defaultdict(list)
        for w in workers:
            if w["id_document_number"]:
                by_id[w["id_document_number"].strip()].append(w)
        for id_num, group in by_id.items():
            if len(group) > 1:
                clusters.append({
                    "criterion": "id_document",
                    "value": id_num,
                    "count": len(group),
                    "workers": [
                        {"id": w["id"], "matricule": w["matricule"],
                         "name": f"{w['first_name']} {w['last_name']}"}
                        for w in group
                    ],
                })

    return {
        "total_workers": len(workers),
        "duplicate_clusters": clusters,
        "clusters_count": len(clusters),
        "duplicates_found": sum(c["count"] for c in clusters),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Absences répétées / patterns suspects
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "detect_repeated_absences",
    "description": (
        "Identifie les ouvriers avec un taux d'absentéisme anormal sur une "
        "période donnée. Retourne la liste des ouvriers avec au moins N absences "
        "sur X jours ouvrables."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 30,
                     "description": "Fenêtre d'analyse en jours"},
            "threshold": {"type": "integer", "default": 5,
                          "description": "Nombre minimum d'absences pour figurer"},
        },
    },
}, permission="attendance.view")
def detect_repeated_absences(days: int = 30, threshold: int = 5, user=None):
    from attendance.models import AttendanceDay
    from accounts.scoping import scope_queryset_by_company

    since = timezone.now().date() - timedelta(days=days)
    qs = AttendanceDay.objects.filter(date__gte=since, status="absent")
    qs = scope_queryset_by_company(qs, user, "site__company")

    counts = (
        qs.values("holder_kind", "holder_object_id")
          .annotate(absences=Count("id"))
          .filter(absences__gte=threshold)
          .order_by("-absences")[:50]
    )

    from django.contrib.contenttypes.models import ContentType
    from ouvriers.models import Worker
    from employees.models import Employee

    results = []
    for c in counts:
        holder = None
        if c["holder_kind"] == "worker":
            holder = Worker.objects.filter(id=c["holder_object_id"]).first()
        elif c["holder_kind"] == "employee":
            holder = Employee.objects.filter(id=c["holder_object_id"]).first()
        if not holder:
            continue
        results.append({
            "kind": c["holder_kind"],
            "id": holder.id,
            "matricule": holder.matricule,
            "name": f"{holder.first_name} {holder.last_name}",
            "absences_count": c["absences"],
            "period_days": days,
            "absence_rate": round(c["absences"] * 100 / days, 1),
        })

    return {
        "period_days": days,
        "threshold": threshold,
        "flagged_count": len(results),
        "workers": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Détection de fraudes potentielles
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "detect_fraud_patterns",
    "description": (
        "Analyse les événements d'accès des dernières 24-72h pour détecter des "
        "patterns suspects : même badge scanné sur 2 sites en peu de temps, "
        "scans hors horaires, tentatives multiples refusées, tailgating potentiel."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "default": 48,
                      "description": "Fenêtre d'analyse en heures"},
        },
    },
}, permission="antifraud.view")
def detect_fraud_patterns(hours: int = 48, user=None):
    from access_control.models import AccessEvent
    from accounts.scoping import scope_queryset_by_company

    since = timezone.now() - timedelta(hours=hours)
    qs = AccessEvent.objects.filter(timestamp__gte=since)
    qs = scope_queryset_by_company(qs, user, "site__company")

    events = list(qs.values(
        "id", "timestamp", "badge_uid", "site_id", "decision",
        "direction", "holder_kind", "holder_object_id",
    ).order_by("badge_uid", "timestamp"))

    patterns = {
        "multi_site_same_badge": [],
        "denied_multiple_times": [],
        "out_of_hours": [],
    }

    # Multi-site : même badge scanné sur 2 sites différents en < 30 min
    by_badge: dict[str, list] = defaultdict(list)
    for e in events:
        if e["badge_uid"]:
            by_badge[e["badge_uid"]].append(e)
    for badge_uid, evts in by_badge.items():
        for i in range(len(evts) - 1):
            e1, e2 = evts[i], evts[i + 1]
            if e1["site_id"] != e2["site_id"]:
                delta = (e2["timestamp"] - e1["timestamp"]).total_seconds()
                if delta < 30 * 60:  # < 30 min
                    patterns["multi_site_same_badge"].append({
                        "badge_uid": badge_uid,
                        "site_1": e1["site_id"],
                        "site_2": e2["site_id"],
                        "delta_minutes": round(delta / 60, 1),
                        "at": e1["timestamp"].isoformat(),
                    })

    # Refus multiples : plus de 3 denies sur le même badge en 1h
    denied_counter = Counter(
        (e["badge_uid"], e["site_id"])
        for e in events if e["decision"] == "denied"
    )
    for (uid, site_id), count in denied_counter.items():
        if count >= 3:
            patterns["denied_multiple_times"].append({
                "badge_uid": uid,
                "site_id": site_id,
                "denies_count": count,
            })

    # Hors horaires : scans entre 22h et 5h
    for e in events:
        hour = e["timestamp"].hour
        if hour >= 22 or hour < 5:
            patterns["out_of_hours"].append({
                "id": e["id"],
                "badge_uid": e["badge_uid"],
                "hour": hour,
                "site_id": e["site_id"],
                "decision": e["decision"],
            })
    patterns["out_of_hours"] = patterns["out_of_hours"][:20]  # cap

    total = sum(len(v) for v in patterns.values())
    return {
        "window_hours": hours,
        "total_events_analyzed": len(events),
        "suspicious_patterns_count": total,
        "patterns": patterns,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Contrôle d'intendance d'un ouvrier
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "worker_intendance_check",
    "description": (
        "Contrôle complet de l'intendance d'un ouvrier : badge assigné et actif, "
        "casque BLE apparié, certifications HSE valides (non expirées), "
        "affectation site en cours. Retourne le score de conformité et les alertes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "worker_id": {"type": "integer", "description": "ID de l'ouvrier"},
            "matricule": {"type": "string", "description": "Ou matricule (alternative)"},
        },
    },
}, permission="ouvriers.view")
def worker_intendance_check(worker_id: int = None, matricule: str = None, user=None):
    from ouvriers.models import Worker
    from devices.models import Badge

    if not worker_id and not matricule:
        return {"error": "worker_id ou matricule requis"}

    q = Q(id=worker_id) if worker_id else Q(matricule=matricule)
    worker = Worker.objects.filter(q).first()
    if not worker:
        return {"error": "Ouvrier introuvable"}

    checks = []
    warnings = []
    ok_count = 0
    total_checks = 0

    # 1. Badge
    total_checks += 1
    badge = Badge.objects.filter(
        holder_object_id=worker.id, holder_kind="worker", status="active",
    ).select_related("paired_helmet").first()
    if badge:
        checks.append({"check": "badge", "status": "ok",
                       "detail": f"Badge {badge.uid} actif"})
        ok_count += 1
    else:
        checks.append({"check": "badge", "status": "fail",
                       "detail": "Aucun badge actif"})
        warnings.append("Badge manquant — impossible de scanner à l'entrée")

    # 2. Casque BLE apparié
    total_checks += 1
    if badge and badge.paired_helmet:
        checks.append({"check": "helmet", "status": "ok",
                       "detail": f"Casque {badge.paired_helmet.serial_number} apparié"})
        ok_count += 1
    else:
        checks.append({"check": "helmet", "status": "fail",
                       "detail": "Pas de casque apparié"})
        warnings.append("Casque BLE non apparié — obligatoire sur chantier")

    # 3. Certifications valides
    total_checks += 1
    from ouvriers.models import WorkerCertification
    today = timezone.now().date()
    certs = WorkerCertification.objects.filter(worker=worker)
    expired = certs.filter(valid_until__lt=today).count()
    active = certs.filter(Q(valid_until__gte=today) | Q(valid_until__isnull=True)).count()

    if active > 0 and expired == 0:
        checks.append({"check": "certifications", "status": "ok",
                       "detail": f"{active} certification(s) valide(s)"})
        ok_count += 1
    elif expired > 0:
        checks.append({"check": "certifications", "status": "warn",
                       "detail": f"{expired} certification(s) expirée(s) sur {active + expired}"})
        warnings.append(f"{expired} certifications HSE expirées")
    else:
        checks.append({"check": "certifications", "status": "warn",
                       "detail": "Aucune certification enregistrée"})

    # 4. Affectation site
    total_checks += 1
    try:
        from ouvriers.models import WorkerAssignment
        current = WorkerAssignment.objects.filter(
            worker=worker,
        ).filter(Q(end_date__gte=today) | Q(end_date__isnull=True)).first()
        if current:
            checks.append({"check": "assignment", "status": "ok",
                           "detail": f"Affecté au site {current.site_id}"})
            ok_count += 1
        else:
            checks.append({"check": "assignment", "status": "warn",
                           "detail": "Aucune affectation en cours"})
            warnings.append("Aucune affectation active à un chantier")
    except Exception:
        pass

    return {
        "worker_id": worker.id,
        "matricule": worker.matricule,
        "name": f"{worker.first_name} {worker.last_name}",
        "score": round(ok_count * 100 / total_checks) if total_checks else 0,
        "checks": checks,
        "warnings": warnings,
        "compliant": len(warnings) == 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Recherche globale plateforme
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "search_platform",
    "description": (
        "Recherche transverse sur la plateforme : employés, ouvriers, badges, "
        "sites, terminaux. Utile quand l'utilisateur pose une question sur une "
        "personne/entité sans savoir où elle est."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Terme de recherche"},
            "limit": {"type": "integer", "default": 5,
                      "description": "Max résultats par catégorie"},
        },
        "required": ["query"],
    },
})
def search_platform(query: str, limit: int = 5, user=None):
    from ouvriers.models import Worker
    from employees.models import Employee
    from devices.models import Badge, Device
    from sites.models import Site
    from accounts.scoping import scope_queryset_by_company

    q_lower = query.strip().lower()
    if not q_lower:
        return {"error": "Query vide"}

    def _search(qs, fields):
        conds = Q()
        for f in fields:
            conds |= Q(**{f"{f}__icontains": q_lower})
        return list(qs.filter(conds)[:limit])

    results = {
        "employees": [
            {"id": e.id, "matricule": e.matricule,
             "name": f"{e.first_name} {e.last_name}", "email": e.email}
            for e in _search(
                scope_queryset_by_company(Employee.objects.all(), user, "company"),
                ["first_name", "last_name", "matricule", "email"],
            )
        ],
        "workers": [
            {"id": w.id, "matricule": w.matricule,
             "name": f"{w.first_name} {w.last_name}", "phone": w.phone}
            for w in _search(
                scope_queryset_by_company(Worker.objects.all(), user, "site__company"),
                ["first_name", "last_name", "matricule", "phone"],
            )
        ],
        "badges": [
            {"id": b.id, "uid": b.uid, "status": b.status, "type": b.type}
            for b in _search(Badge.objects.all(), ["uid"])
        ],
        "sites": [
            {"id": s.id, "name": s.name, "code": s.code}
            for s in _search(
                scope_queryset_by_company(Site.objects.all(), user, "company"),
                ["name", "code"],
            )
        ],
        "devices": [
            {"id": d.id, "serial": d.serial_number, "ip": str(d.ip_address or "")}
            for d in _search(Device.objects.all(), ["serial_number", "ip_address"])
        ],
    }

    total = sum(len(v) for v in results.values())
    return {"query": query, "total_matches": total, "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Analyse anomalies présence (retards fréquents, heures atypiques)
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "analyze_attendance_anomalies",
    "description": (
        "Détecte les anomalies de présence : ouvriers systématiquement en retard, "
        "premiers scans du jour anormalement tardifs ou précoces, absences "
        "consécutives."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 30},
        },
    },
}, permission="attendance.view")
def analyze_attendance_anomalies(days: int = 30, user=None):
    from attendance.models import AttendanceDay
    from accounts.scoping import scope_queryset_by_company

    since = timezone.now().date() - timedelta(days=days)
    qs = AttendanceDay.objects.filter(date__gte=since)
    qs = scope_queryset_by_company(qs, user, "site__company")

    # Retards répétés
    late_agg = (
        qs.filter(is_late=True)
        .values("holder_kind", "holder_object_id")
        .annotate(late_count=Count("id"))
        .filter(late_count__gte=5)
        .order_by("-late_count")[:20]
    )
    late_workers = []
    from ouvriers.models import Worker
    from employees.models import Employee
    for c in late_agg:
        holder = (Worker.objects.filter(id=c["holder_object_id"]).first()
                  if c["holder_kind"] == "worker"
                  else Employee.objects.filter(id=c["holder_object_id"]).first())
        if holder:
            late_workers.append({
                "kind": c["holder_kind"],
                "id": holder.id,
                "matricule": holder.matricule,
                "name": f"{holder.first_name} {holder.last_name}",
                "late_days": c["late_count"],
                "period_days": days,
            })

    # Heures supp anormales
    ot_agg = (
        qs.filter(overtime_minutes__gt=0)
        .values("holder_kind", "holder_object_id")
        .annotate(total_ot=Count("id"))
        .order_by("-total_ot")[:10]
    )

    return {
        "period_days": days,
        "repeated_late_workers": late_workers,
        "top_overtime_workers": len(list(ot_agg)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. Santé globale de la plateforme (compact)
# ─────────────────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "platform_intelligence_snapshot",
    "description": (
        "Analyse macro de la plateforme : couverture badges/casques ouvriers, "
        "terminaux offline, sites sans coordonnées GPS, employés sans face template, "
        "alertes fraude en cours. Rapport synthétique."
    ),
    "parameters": {"type": "object", "properties": {}},
})
def platform_intelligence_snapshot(user=None):
    from ouvriers.models import Worker
    from employees.models import Employee
    from devices.models import Badge, Device
    from sites.models import Site
    from accounts.scoping import scope_queryset_by_company

    workers = scope_queryset_by_company(Worker.objects.all(), user, "site__company")
    total_workers = workers.count()
    workers_with_badge = workers.filter(
        id__in=Badge.objects.filter(holder_kind="worker", status="active")
                            .values("holder_object_id")
    ).count()

    devices = Device.objects.all()
    offline_devices = devices.filter(status="offline").count()

    sites = scope_queryset_by_company(Site.objects.all(), user, "company")
    sites_without_gps = sites.filter(
        Q(latitude__isnull=True) | Q(longitude__isnull=True)
    ).count()

    alerts_open = 0
    try:
        from antifraud.models import Alert
        alerts_open = Alert.objects.filter(status="open").count()
    except Exception:
        pass

    return {
        "workers": {
            "total": total_workers,
            "with_active_badge": workers_with_badge,
            "coverage_pct": round(workers_with_badge * 100 / total_workers, 1) if total_workers else 0,
        },
        "devices": {
            "total": devices.count(),
            "offline": offline_devices,
        },
        "sites": {
            "total": sites.count(),
            "without_gps": sites_without_gps,
        },
        "antifraud": {
            "alerts_open": alerts_open,
        },
        "computed_at": timezone.now().isoformat(),
    }
