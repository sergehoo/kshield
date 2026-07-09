"""Catalogue de tools que l'IA peut appeler via function-calling OpenAI/DeepSeek.

Chaque tool est une fonction Python déclarée avec :
- son **schéma JSON** (pour que le LLM sache l'appeler)
- son **handler** qui interroge la vraie base Shield
- son **RBAC** (permissions requises)

Le service AIChatService (voir services.py) fait la boucle :
  LLM → décide d'appeler tool → tool exécute → résultat renvoyé → LLM formule réponse.

Ajouter un nouveau tool :
  1. Écrire la fonction (queryset Django → dict/list sérialisable JSON)
  2. Décorer avec @register_tool(schema=..., permission=...)
  3. Il est automatiquement exposé au LLM.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Callable, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Registry des tools
# ─────────────────────────────────────────────────────────────────────────────
_TOOLS: dict[str, dict] = {}   # name → {handler, schema, permission, is_action}


def register_tool(schema: dict, permission: Optional[str] = None,
                  is_action: bool = False):
    """Décorateur pour enregistrer un tool.

    Args:
        schema: schema OpenAI function-calling (name/description/parameters).
        permission: code RBAC requis (ex. "devices.manage"). None = read-only public.
        is_action: True si le tool modifie l'état (nécessite confirmation UI).
    """
    def _decorator(fn: Callable):
        name = schema.get("name") or fn.__name__
        _TOOLS[name] = {
            "handler": fn,
            "schema": schema,
            "permission": permission,
            "is_action": is_action,
        }
        return fn
    return _decorator


def get_tool_schemas_for_llm() -> list[dict]:
    """Renvoie la liste des tools au format OpenAI function-calling."""
    return [
        {"type": "function", "function": t["schema"]}
        for t in _TOOLS.values()
    ]


def execute_tool(name: str, arguments: dict, user=None) -> dict:
    """Exécute un tool par son nom + args.

    Vérifie RBAC. Log audit. Retourne toujours un dict sérialisable.
    """
    tool = _TOOLS.get(name)
    if not tool:
        return {"error": f"Tool inconnu : {name}"}

    # RBAC
    if tool["permission"] and user:
        try:
            from accounts.rbac import user_has_permission
            if not (user.is_superuser
                    or user_has_permission(user, tool["permission"])):
                return {"error": f"Permission refusée : {tool['permission']}"}
        except Exception as exc:
            logger.warning("RBAC check failed for %s: %s", name, exc)

    # Log audit pour les actions
    if tool["is_action"]:
        try:
            _log_audit(name, arguments, user)
        except Exception:
            logger.exception("Audit log failed for %s", name)

    import time as _time
    _t0 = _time.monotonic()
    try:
        result = tool["handler"](**(arguments or {}))
        # S'assurer que le résultat est JSON-sérialisable
        json.dumps(result, default=str)
        _dt = int((_time.monotonic() - _t0) * 1000)
        if _dt > 1000:
            logger.warning("[SLOW TOOL] %s took %d ms (args=%s)",
                            name, _dt, str(arguments)[:80])
        else:
            logger.info("[tool] %s ran in %d ms", name, _dt)
        return result
    except Exception as exc:
        _dt = int((_time.monotonic() - _t0) * 1000)
        logger.exception("Tool %s failed after %d ms", name, _dt)
        return {"error": f"Erreur exécution : {str(exc)[:200]}"}


def _log_audit(tool_name: str, args: dict, user):
    """Trace chaque action IA dans le log d'audit."""
    try:
        from audit.models import AuditLog
        AuditLog.objects.create(
            actor=user if user and user.is_authenticated else None,
            action=f"ai_tool.{tool_name}",
            payload={"args": args},
        )
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════════════
# TOOLS : LECTURE (read-only)
# ═════════════════════════════════════════════════════════════════════════════

# ── Équipements ─────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "list_devices",
    "description": (
        "Liste les équipements connectés à Shield (terminaux d'accès, lecteurs "
        "RFID/NFC/BLE, portiques UHF, terminaux face, caméras, gateways). "
        "Filtres possibles par site, statut ou type."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site_id":   {"type": "integer", "description": "ID du site pour filtrer"},
            "status":    {"type": "string", "enum": ["active", "inactive", "maintenance", "lost"]},
            "type":      {"type": "string", "description": "Type de device (reader_uhf_fixed, face_terminal, portique, camera, beacon_ble…)"},
            "limit":     {"type": "integer", "default": 50, "maximum": 200},
        },
    },
})
def list_devices(site_id=None, status=None, type=None, limit=50):
    from devices.models import Device
    qs = Device.objects.select_related("model", "site").all()
    if site_id:   qs = qs.filter(site_id=site_id)
    if status:    qs = qs.filter(status=status)
    if type:      qs = qs.filter(model__type=type)
    qs = qs.order_by("serial_number")[: max(1, min(int(limit), 200))]

    now = timezone.now()
    items = []
    for d in qs:
        last_hb = d.last_heartbeat_at
        online = bool(last_hb and (now - last_hb) < timedelta(minutes=5))
        items.append({
            "id": d.pk,
            "serial": d.serial_number,
            "brand": d.model.brand if d.model else None,
            "model": d.model.model if d.model else None,
            "type": d.model.type if d.model else None,
            "site": d.site.name if d.site else None,
            "ip": d.ip_address,
            "mac": d.mac_address,
            "firmware": d.firmware_version,
            "battery": d.battery_level,
            "status": d.status,
            "online": online,
            "last_heartbeat": last_hb.isoformat() if last_hb else None,
            "url": f"/devices-mng/{d.pk}/",
        })
    return {"count": len(items), "devices": items}


@register_tool(schema={
    "name": "list_offline_devices",
    "description": "Liste les équipements hors-ligne (sans heartbeat depuis N minutes).",
    "parameters": {
        "type": "object",
        "properties": {
            "minutes": {"type": "integer", "default": 5, "description": "Seuil en minutes"},
            "limit":   {"type": "integer", "default": 30, "maximum": 100},
        },
    },
})
def list_offline_devices(minutes=5, limit=30):
    from django.db.models import Q
    from devices.models import Device
    cutoff = timezone.now() - timedelta(minutes=int(minutes))
    qs = (Device.objects.select_related("model", "site")
          .filter(Q(last_heartbeat_at__isnull=True)
                  | Q(last_heartbeat_at__lt=cutoff))
          .filter(status="active")
          .order_by("-last_heartbeat_at")[: max(1, min(int(limit), 100))])
    items = []
    for d in qs:
        items.append({
            "id": d.pk, "serial": d.serial_number,
            "brand": d.model.brand if d.model else None,
            "model": d.model.model if d.model else None,
            "type": d.model.type if d.model else None,
            "site": d.site.name if d.site else None,
            "ip": d.ip_address,
            "last_heartbeat": d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else None,
            "url": f"/devices-mng/{d.pk}/",
        })
    return {"count": len(items), "offline_devices": items,
            "threshold_minutes": int(minutes)}


@register_tool(schema={
    "name": "get_device_details",
    "description": "Récupère la fiche complète d'un équipement par son ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "device_id": {"type": "integer"},
        },
        "required": ["device_id"],
    },
})
def get_device_details(device_id):
    from devices.models import Device
    try:
        d = Device.objects.select_related(
            "model", "site", "zone", "checkpoint",
        ).get(pk=int(device_id))
    except Device.DoesNotExist:
        return {"error": f"Équipement {device_id} introuvable"}
    return {
        "id": d.pk, "serial": d.serial_number,
        "brand": d.model.brand if d.model else None,
        "model": d.model.model if d.model else None,
        "type": d.model.type if d.model else None,
        "spec": d.model.spec if d.model else None,
        "site": {"id": d.site.pk, "name": d.site.name} if d.site else None,
        "zone": d.zone.name if d.zone else None,
        "checkpoint": d.checkpoint.name if d.checkpoint else None,
        "ip": d.ip_address, "mac": d.mac_address,
        "firmware": d.firmware_version, "battery": d.battery_level,
        "status": d.status,
        "commissioned_at": d.commissioned_at.isoformat() if d.commissioned_at else None,
        "last_heartbeat": d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else None,
        "url": f"/devices-mng/{d.pk}/",
    }


# ── Présence & pointage ─────────────────────────────────────────────────────
@register_tool(schema={
    "name": "count_present_now",
    "description": (
        "Compte les personnes actuellement présentes sur un site (dernier pointage "
        "était une entrée, pas de sortie après). Filtre optionnel par site."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "site_id": {"type": "integer"},
            "kind":    {"type": "string", "enum": ["employee", "worker", "visitor", "all"], "default": "all"},
        },
    },
})
def count_present_now(site_id=None, kind="all"):
    """Compte les personnes présentes en 1 seule requête SQL (fenêtre analytique).

    Anciennement N+1 : pour chaque personne, une requête pour trouver son
    dernier direction. Maintenant : DISTINCT ON (holder) ORDER BY timestamp DESC.
    """
    from django.db import connection
    from django.db.models import F, Max

    today = timezone.localdate()

    # Sous-requête : le dernier event de chaque personne aujourd'hui.
    # On utilise Postgres DISTINCT ON (rapide, 1 seule query).
    where_clauses = ["timestamp::date = %s",
                     "decision = 'granted'",
                     "holder_object_id IS NOT NULL"]
    params = [today]
    if site_id:
        where_clauses.append("site_id = %s")
        params.append(int(site_id))
    if kind and kind != "all":
        where_clauses.append("holder_kind = %s")
        params.append(kind)
    where_sql = " AND ".join(where_clauses)

    sql = f"""
        SELECT holder_kind, COUNT(*) AS n
        FROM (
          SELECT DISTINCT ON (holder_kind, holder_object_id)
                 holder_kind, holder_object_id, direction
          FROM access_control_accessevent
          WHERE {where_sql}
          ORDER BY holder_kind, holder_object_id, timestamp DESC
        ) latest
        WHERE direction = 'in'
        GROUP BY holder_kind
    """
    detail = {"employee": 0, "worker": 0, "visitor": 0}
    try:
        with connection.cursor() as c:
            c.execute(sql, params)
            for row in c.fetchall():
                detail[row[0]] = row[1]
    except Exception:
        # Fallback SQLite / DB non-Postgres : requête ORM plus lente mais safe
        return _count_present_fallback(site_id, kind)

    return {
        "total_present": sum(detail.values()),
        "by_kind": detail,
        "site_id": site_id,
        "computed_at": timezone.now().isoformat(),
    }


def _count_present_fallback(site_id, kind):
    """Fallback ORM (SQLite ou si DISTINCT ON pas supporté)."""
    from access_control.models import AccessEvent
    from django.db.models import Max
    today = timezone.localdate()
    qs = AccessEvent.objects.filter(
        timestamp__date=today, decision="granted",
        holder_object_id__isnull=False,
    )
    if site_id: qs = qs.filter(site_id=site_id)
    if kind and kind != "all": qs = qs.filter(holder_kind=kind)

    # Bulk : récup tous les events du jour puis on garde le dernier par personne
    last_by_person = {}
    for e in qs.order_by("timestamp").only(
        "holder_kind", "holder_object_id", "direction",
    )[:5000]:   # cap sécurité pour éviter d'exploser la mémoire
        key = (e.holder_kind, e.holder_object_id)
        last_by_person[key] = e.direction

    detail = {"employee": 0, "worker": 0, "visitor": 0}
    for (hk, _), direction in last_by_person.items():
        if direction == "in":
            detail[hk] = detail.get(hk, 0) + 1
    return {
        "total_present": sum(detail.values()),
        "by_kind": detail,
        "site_id": site_id,
        "computed_at": timezone.now().isoformat(),
        "fallback": True,
    }


@register_tool(schema={
    "name": "attendance_summary_today",
    "description": "Résumé du pointage du jour : entrées/sorties/refus par site.",
    "parameters": {"type": "object", "properties": {
        "site_id": {"type": "integer"},
    }},
})
def attendance_summary_today(site_id=None):
    """Résumé pointage — 1 seule requête agrégée (au lieu de 5)."""
    from django.db.models import Count, Q
    from access_control.models import AccessEvent
    today = timezone.localdate()
    qs = AccessEvent.objects.filter(timestamp__date=today)
    if site_id: qs = qs.filter(site_id=site_id)

    # Aggregat en 1 requête via Q filters (au lieu de 5 requêtes séquentielles)
    agg = qs.aggregate(
        total=Count("id"),
        granted=Count("id", filter=Q(decision="granted")),
        denied=Count("id", filter=Q(decision="denied")),
        entries=Count("id", filter=Q(direction="in", decision="granted")),
        exits=Count("id", filter=Q(direction="out", decision="granted")),
    )
    by_site = list(
        qs.values("site__name").annotate(n=Count("id"))
        .order_by("-n")[:10]
    )
    return {
        "date": today.isoformat(),
        "total_scans": agg["total"],
        "granted": agg["granted"], "denied": agg["denied"],
        "entries": agg["entries"], "exits": agg["exits"],
        "top_sites": [{"site": s["site__name"] or "?", "scans": s["n"]}
                      for s in by_site],
    }


# ── Employés / Ouvriers ─────────────────────────────────────────────────────
@register_tool(schema={
    "name": "search_person",
    "description": "Recherche employé, ouvrier ou visiteur par nom, matricule, email ou téléphone.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Terme de recherche (min 2 caractères)"},
            "kind":  {"type": "string", "enum": ["employee", "worker", "visitor", "all"], "default": "all"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
})
def search_person(query, kind="all", limit=10):
    from django.db.models import Q
    q = str(query or "").strip()
    if len(q) < 2:
        return {"error": "Query trop courte (min 2 caractères)"}
    results = []
    if kind in ("all", "employee"):
        from employees.models import Employee
        for e in Employee.objects.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(matricule__icontains=q) | Q(email__icontains=q)
            | Q(phone__icontains=q),
        )[:limit]:
            results.append({
                "kind": "employee", "id": e.pk, "matricule": e.matricule,
                "name": f"{e.first_name} {e.last_name}", "email": e.email,
                "phone": e.phone, "status": e.status,
                "url": f"/employees/{e.pk}/",
            })
    if kind in ("all", "worker"):
        from ouvriers.models import Worker
        for w in Worker.objects.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(matricule__icontains=q),
        )[:limit]:
            results.append({
                "kind": "worker", "id": w.pk, "matricule": w.matricule,
                "name": f"{w.first_name} {w.last_name}",
                "phone": w.phone, "status": w.status,
                "url": f"/workers/{w.pk}/",
            })
    return {"count": len(results), "results": results, "query": q}


# ── Sites & entreprises ─────────────────────────────────────────────────────
@register_tool(schema={
    "name": "list_sites",
    "description": "Liste tous les sites de la plateforme (usines, chantiers, bureaux).",
    "parameters": {"type": "object", "properties": {}},
})
def list_sites():
    from sites.models import Site
    items = []
    for s in Site.objects.select_related("company").order_by("name")[:100]:
        items.append({
            "id": s.pk, "code": s.code, "name": s.name,
            "type": s.type, "status": s.status,
            "company": s.company.name if s.company else None,
            "url": f"/sites/{s.pk}/",
        })
    return {"count": len(items), "sites": items}


@register_tool(schema={
    "name": "list_companies",
    "description": "Liste les entreprises/filiales enregistrées.",
    "parameters": {"type": "object", "properties": {}},
})
def list_companies():
    from core.models import Company
    items = []
    for c in Company.objects.order_by("name")[:100]:
        items.append({
            "id": c.pk, "code": c.code, "name": c.name,
            "legal_name": getattr(c, "legal_name", ""),
            "sector": getattr(c, "sector", ""),
            "is_active": c.is_active,
        })
    return {"count": len(items), "companies": items}


# ── Badges ──────────────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "count_badges",
    "description": "Statistiques badges par catégorie et statut.",
    "parameters": {"type": "object", "properties": {}},
})
def count_badges():
    from devices.models import Badge
    from django.db.models import Count
    stats = list(
        Badge.objects.values("category", "status")
        .annotate(n=Count("id")).order_by("-n")
    )
    return {"stats": stats, "total": sum(s["n"] for s in stats)}


# ── Accès & événements ─────────────────────────────────────────────────────
@register_tool(schema={
    "name": "recent_access_events",
    "description": "Liste les derniers événements d'accès (pointages, refus).",
    "parameters": {
        "type": "object",
        "properties": {
            "limit":    {"type": "integer", "default": 20, "maximum": 100},
            "decision": {"type": "string", "enum": ["granted", "denied", "review"]},
            "site_id":  {"type": "integer"},
        },
    },
})
def recent_access_events(limit=20, decision=None, site_id=None):
    from access_control.models import AccessEvent
    qs = AccessEvent.objects.select_related("site", "device").order_by("-timestamp")
    if decision: qs = qs.filter(decision=decision)
    if site_id:  qs = qs.filter(site_id=site_id)
    items = []
    for e in qs[: max(1, min(int(limit), 100))]:
        items.append({
            "id": e.pk, "timestamp": e.timestamp.isoformat(),
            "site": e.site.name if e.site else None,
            "device": e.device.serial_number if e.device else None,
            "badge_uid": e.badge_uid,
            "direction": e.direction, "method": e.method,
            "decision": e.decision,
            "denial_reason": e.denial_reason,
            "holder_kind": e.holder_kind,
        })
    return {"count": len(items), "events": items}


@register_tool(schema={
    "name": "recent_incidents",
    "description": "Liste les incidents anti-fraude / alertes récentes.",
    "parameters": {
        "type": "object",
        "properties": {
            "hours":   {"type": "integer", "default": 24},
            "status":  {"type": "string", "enum": ["open", "acknowledged", "resolved", "false_positive"]},
            "limit":   {"type": "integer", "default": 15},
        },
    },
})
def recent_incidents(hours=24, status=None, limit=15):
    try:
        from antifraud.models import FraudAlert
    except ImportError:
        return {"count": 0, "incidents": []}
    since = timezone.now() - timedelta(hours=int(hours))
    qs = FraudAlert.objects.filter(created_at__gte=since).order_by("-created_at")
    if status:
        qs = qs.filter(status=status)
    items = []
    for a in qs[: max(1, min(int(limit), 100))]:
        items.append({
            "id": a.pk,
            "created_at": a.created_at.isoformat(),
            "kind": getattr(a, "kind", ""),
            "severity": getattr(a, "severity", ""),
            "status": getattr(a, "status", ""),
            "reason": getattr(a, "reason", "") or getattr(a, "description", ""),
        })
    return {"count": len(items), "incidents": items,
            "since_hours": int(hours)}


# ── Dashboard global ────────────────────────────────────────────────────────
@register_tool(schema={
    "name": "platform_snapshot",
    "description": (
        "Vue synthétique de la plateforme : total employés, ouvriers, sites, "
        "devices online/offline, présences aujourd'hui, refus 24h. "
        "Utile pour répondre à 'Fais un état des lieux'."
    ),
    "parameters": {"type": "object", "properties": {}},
})
def platform_snapshot():
    from django.db.models import Q
    now = timezone.now()
    today = timezone.localdate()
    cutoff = now - timedelta(minutes=5)

    from devices.models import Device, Badge
    from employees.models import Employee
    from ouvriers.models import Worker
    from sites.models import Site
    from access_control.models import AccessEvent

    snap = {
        "computed_at": now.isoformat(),
        "employees_total": Employee.objects.count(),
        "employees_active": Employee.objects.filter(status="active").count(),
        "workers_total": Worker.objects.count(),
        "workers_active": Worker.objects.filter(status="active").count(),
        "sites_total": Site.objects.count(),
        "sites_active": Site.objects.filter(status="active").count(),
        "badges_active": Badge.objects.filter(status="active").count(),
        "badges_pool": Badge.objects.filter(status="available").count(),
        "devices_total": Device.objects.count(),
        "devices_online": Device.objects.filter(
            status="active", last_heartbeat_at__gte=cutoff,
        ).count(),
        "devices_offline": Device.objects.filter(
            status="active",
        ).filter(
            Q(last_heartbeat_at__isnull=True) | Q(last_heartbeat_at__lt=cutoff),
        ).count(),
        "scans_today": AccessEvent.objects.filter(timestamp__date=today).count(),
        "denied_24h": AccessEvent.objects.filter(
            timestamp__gte=now - timedelta(hours=24), decision="denied",
        ).count(),
    }
    try:
        from antifraud.models import FraudAlert
        snap["alerts_open"] = FraudAlert.objects.filter(status="open").count()
    except Exception:
        snap["alerts_open"] = 0
    return snap


# ═════════════════════════════════════════════════════════════════════════════
# TOOLS : ACTIONS (RBAC-checked)
# ═════════════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════════════
# TOOLS : CRÉATION d'entités métier (RBAC-checked)
# ═════════════════════════════════════════════════════════════════════════════

@register_tool(
    schema={
        "name": "create_sites_bulk",
        "description": (
            "Crée plusieurs sites en une seule opération. Idempotent : si un site "
            "avec le même nom existe déjà, il est skipé (pas de doublon). "
            "Utilise-moi quand l'user demande de créer plusieurs sites d'un coup."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Liste des noms de sites à créer",
                },
                "company_id": {"type": "integer", "description": "ID de la company associée (optionnel)"},
                "site_type":  {"type": "string", "default": "office",
                                "enum": ["office", "warehouse", "site_construction", "site_industrial", "other"]},
            },
            "required": ["names"],
        },
    },
    permission="sites.manage",
    is_action=True,
)
def create_sites_bulk(names, company_id=None, site_type="office"):
    from sites.models import Site
    from core.services import get_current_tenant, get_kaydan_tenant
    from django.utils.text import slugify

    if not names or not isinstance(names, list):
        return {"error": "names doit être une liste non vide"}

    tenant = get_current_tenant() or get_kaydan_tenant()
    company = None
    if company_id:
        try:
            from core.models import Company
            company = Company.objects.get(pk=int(company_id))
        except Exception:
            company = None

    created = []; skipped = []; errors = []
    for raw_name in names[:20]:   # cap sécurité
        name = str(raw_name or "").strip()
        if not name:
            continue
        code = slugify(name)[:32].upper() or f"SITE-{len(created)+1}"
        try:
            site, was_created = Site.objects.get_or_create(
                tenant=tenant, name=name,
                defaults={
                    "code": code,
                    "type": site_type,
                    "status": "active",
                    "company": company,
                },
            )
            if was_created:
                created.append({"id": site.pk, "name": site.name, "code": site.code,
                                 "url": f"/sites/{site.pk}/"})
            else:
                skipped.append({"id": site.pk, "name": site.name})
        except Exception as exc:
            errors.append({"name": name, "error": str(exc)[:200]})

    return {
        "created": created, "created_count": len(created),
        "skipped": skipped, "skipped_count": len(skipped),
        "errors": errors,
        "message": f"{len(created)} sites créés, {len(skipped)} déjà existants, "
                    f"{len(errors)} erreurs.",
    }


@register_tool(
    schema={
        "name": "create_site",
        "description": "Crée un site (usine, chantier, bureau) unique avec ses paramètres.",
        "parameters": {
            "type": "object",
            "properties": {
                "name":       {"type": "string"},
                "code":       {"type": "string", "description": "Code court (auto si vide)"},
                "site_type":  {"type": "string", "enum": ["office", "warehouse", "site_construction", "site_industrial", "other"], "default": "office"},
                "company_id": {"type": "integer"},
                "address":    {"type": "string"},
                "latitude":   {"type": "number"},
                "longitude":  {"type": "number"},
            },
            "required": ["name"],
        },
    },
    permission="sites.manage",
    is_action=True,
)
def create_site(name, code=None, site_type="office", company_id=None,
                address=None, latitude=None, longitude=None):
    from sites.models import Site
    from core.services import get_current_tenant, get_kaydan_tenant
    from django.utils.text import slugify

    tenant = get_current_tenant() or get_kaydan_tenant()
    company = None
    if company_id:
        try:
            from core.models import Company
            company = Company.objects.get(pk=int(company_id))
        except Exception:
            pass

    if not code:
        code = slugify(name)[:32].upper()

    defaults = {"code": code, "type": site_type, "status": "active",
                "company": company}
    if latitude is not None:  defaults["latitude"] = latitude
    if longitude is not None: defaults["longitude"] = longitude

    site, created = Site.objects.get_or_create(
        tenant=tenant, name=name, defaults=defaults,
    )
    return {
        "created": created, "id": site.pk, "name": site.name, "code": site.code,
        "url": f"/sites/{site.pk}/",
        "message": (f"✓ Site '{name}' créé (ID {site.pk})" if created
                    else f"↻ Site '{name}' existait déjà (ID {site.pk})"),
    }


@register_tool(
    schema={
        "name": "create_company",
        "description": "Crée une entreprise / filiale.",
        "parameters": {
            "type": "object",
            "properties": {
                "name":       {"type": "string"},
                "code":       {"type": "string"},
                "legal_name": {"type": "string"},
                "sector":     {"type": "string"},
            },
            "required": ["name"],
        },
    },
    permission="companies.manage",
    is_action=True,
)
def create_company(name, code=None, legal_name=None, sector=None):
    from core.models import Company
    from core.services import get_current_tenant, get_kaydan_tenant
    from django.utils.text import slugify

    tenant = get_current_tenant() or get_kaydan_tenant()
    if not code:
        code = slugify(name)[:24].upper()
    defaults = {"code": code, "legal_name": legal_name or name,
                "is_active": True}
    if sector: defaults["sector"] = sector

    c, created = Company.objects.get_or_create(
        tenant=tenant, name=name, defaults=defaults,
    )
    return {
        "created": created, "id": c.pk, "name": c.name, "code": c.code,
        "message": (f"✓ Entreprise '{name}' créée" if created
                    else f"↻ Entreprise '{name}' existait déjà"),
    }


@register_tool(
    schema={
        "name": "create_employee",
        "description": "Crée un employé (bureau, cadre). Pour un ouvrier chantier, utilise create_worker.",
        "parameters": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name":  {"type": "string"},
                "matricule":  {"type": "string", "description": "Auto-généré si vide"},
                "email":      {"type": "string"},
                "phone":      {"type": "string"},
                "site_id":    {"type": "integer"},
                "position":   {"type": "string"},
            },
            "required": ["first_name", "last_name"],
        },
    },
    permission="employees.manage",
    is_action=True,
)
def create_employee(first_name, last_name, matricule=None, email=None,
                    phone=None, site_id=None, position=None):
    from employees.models import Employee
    from core.services import get_current_tenant, get_kaydan_tenant

    tenant = get_current_tenant() or get_kaydan_tenant()
    if not matricule:
        # Auto-générer : EMP-<prefix>-<count>
        count = Employee.objects.count() + 1
        matricule = f"EMP-{count:04d}"

    defaults = {"first_name": first_name, "last_name": last_name,
                "status": "active"}
    if email:   defaults["email"] = email
    if phone:   defaults["phone"] = phone
    if position: defaults["position"] = position

    try:
        e, created = Employee.objects.get_or_create(
            tenant=tenant, matricule=matricule, defaults=defaults,
        )
    except Exception as exc:
        return {"error": f"Impossible de créer l'employé : {exc}"}
    return {
        "created": created, "id": e.pk, "matricule": e.matricule,
        "name": f"{e.first_name} {e.last_name}",
        "url": f"/employees/{e.pk}/",
    }


@register_tool(
    schema={
        "name": "create_worker",
        "description": "Crée un ouvrier chantier (nécessite casque UHF+BLE pour le pointage).",
        "parameters": {
            "type": "object",
            "properties": {
                "first_name":       {"type": "string"},
                "last_name":        {"type": "string"},
                "matricule":        {"type": "string"},
                "phone":            {"type": "string"},
                "trade":            {"type": "string", "description": "Métier (maçon, électricien, …)"},
                "subcontractor_id": {"type": "integer"},
            },
            "required": ["first_name", "last_name"],
        },
    },
    permission="workers.manage",
    is_action=True,
)
def create_worker(first_name, last_name, matricule=None, phone=None,
                  trade=None, subcontractor_id=None):
    from ouvriers.models import Worker
    from core.services import get_current_tenant, get_kaydan_tenant

    tenant = get_current_tenant() or get_kaydan_tenant()
    if not matricule:
        count = Worker.objects.count() + 1
        matricule = f"WKR-{count:04d}"

    defaults = {"first_name": first_name, "last_name": last_name,
                "status": "active"}
    if phone: defaults["phone"] = phone
    if trade: defaults["trade"] = trade

    try:
        w, created = Worker.objects.get_or_create(
            tenant=tenant, matricule=matricule, defaults=defaults,
        )
    except Exception as exc:
        return {"error": f"Impossible de créer l'ouvrier : {exc}"}
    return {
        "created": created, "id": w.pk, "matricule": w.matricule,
        "name": f"{w.first_name} {w.last_name}",
        "url": f"/workers/{w.pk}/",
    }


@register_tool(
    schema={
        "name": "sync_zkteco_device",
        "description": "Force la synchronisation immédiate d'un terminal ZKTeco (pull pointages).",
        "parameters": {
            "type": "object",
            "properties": {"device_id": {"type": "integer"}},
            "required": ["device_id"],
        },
    },
    permission="devices.manage",
    is_action=True,
)
def sync_zkteco_device(device_id):
    from devices.tasks import sync_zkteco_attendances
    try:
        result = sync_zkteco_attendances(device_id=int(device_id))
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@register_tool(
    schema={
        "name": "push_employee_to_terminals",
        "description": "Provisionne un employé sur tous les terminaux ZKTeco (immédiat).",
        "parameters": {
            "type": "object",
            "properties": {"employee_id": {"type": "integer"}},
            "required": ["employee_id"],
        },
    },
    permission="employees.manage",
    is_action=True,
)
def push_employee_to_terminals(employee_id):
    from devices.tasks import push_zkteco_users
    from employees.models import Employee
    from devices.models import Badge
    from django.contrib.contenttypes.models import ContentType
    try:
        emp = Employee.objects.get(pk=int(employee_id))
    except Employee.DoesNotExist:
        return {"error": "Employé introuvable"}
    ct = ContentType.objects.get_for_model(Employee)
    badge = Badge.objects.filter(
        holder_content_type=ct, holder_object_id=emp.pk,
        status__in=("active", "assigned"),
    ).first()
    if not badge:
        return {"error": "Aucun badge actif pour cet employé"}
    result = push_zkteco_users()   # push all
    return {"ok": True, "employee": str(emp), "badge_uid": badge.uid,
            "result": result}


@register_tool(
    schema={
        "name": "suspend_badge",
        "description": "Suspend un badge (blocage temporaire, révocable). Utile en cas de perte suspecte.",
        "parameters": {
            "type": "object",
            "properties": {
                "badge_id": {"type": "integer"},
                "reason":   {"type": "string", "description": "Raison de la suspension"},
            },
            "required": ["badge_id", "reason"],
        },
    },
    permission="badges.manage",
    is_action=True,
)
def suspend_badge(badge_id, reason):
    from devices.models import Badge
    from devices.services import BadgeWorkflowService
    try:
        b = Badge.objects.get(pk=int(badge_id))
    except Badge.DoesNotExist:
        return {"error": "Badge introuvable"}
    try:
        BadgeWorkflowService.suspend(b, reason=str(reason)[:200], by_user=None)
        return {"ok": True, "badge_uid": b.uid, "status": b.status,
                "reason": reason}
    except Exception as exc:
        return {"error": str(exc)[:200]}


@register_tool(
    schema={
        "name": "revoke_badge",
        "description": "Révoque définitivement un badge (perdu, ex-employé). Irréversible.",
        "parameters": {
            "type": "object",
            "properties": {
                "badge_id": {"type": "integer"},
                "reason":   {"type": "string"},
            },
            "required": ["badge_id", "reason"],
        },
    },
    permission="badges.manage",
    is_action=True,
)
def revoke_badge(badge_id, reason):
    from devices.models import Badge
    from devices.services import BadgeWorkflowService
    try:
        b = Badge.objects.get(pk=int(badge_id))
    except Badge.DoesNotExist:
        return {"error": "Badge introuvable"}
    try:
        BadgeWorkflowService.revoke(b, reason=str(reason)[:200], by_user=None)
        return {"ok": True, "badge_uid": b.uid, "status": b.status,
                "reason": reason}
    except Exception as exc:
        return {"error": str(exc)[:200]}


@register_tool(
    schema={
        "name": "run_device_connectivity_test",
        "description": "Lance un test de connectivité (ping + TCP + protocole) sur un équipement.",
        "parameters": {
            "type": "object",
            "properties": {"device_id": {"type": "integer"}},
            "required": ["device_id"],
        },
    },
    permission="devices.view",
    is_action=False,   # read-only, pas besoin de confirmation
)
def run_device_connectivity_test(device_id):
    # Réutilise la logique du DeviceConnectivityTestView.
    # Ici on retourne une réponse simplifiée.
    from devices.models import Device
    import socket
    try:
        d = Device.objects.get(pk=int(device_id))
    except Device.DoesNotExist:
        return {"error": "Équipement introuvable"}
    if not d.ip_address:
        return {"error": "Pas d'IP renseignée pour ce device"}
    # Test rapide sur 3 ports principaux
    ports_to_test = [80, 443, 4370, 5084, 554]
    open_ports = []
    for port in ports_to_test:
        try:
            with socket.socket() as s:
                s.settimeout(1.0)
                if s.connect_ex((d.ip_address, port)) == 0:
                    open_ports.append(port)
        except Exception:
            pass
    return {
        "device": d.serial_number,
        "ip": d.ip_address,
        "reachable": bool(open_ports),
        "open_ports": open_ports,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Import des tools d'analyse avancée (détection fraudes, doublons, absences)
# Le simple import déclenche les @register_tool.
# ─────────────────────────────────────────────────────────────────────────────
from . import analysis_tools  # noqa: E402, F401
