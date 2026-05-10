"""KAYDAN SHIELD — Service d'insights métier pour la page Rapports & KPI.

Calcule de façon déterministe (sans LLM nécessaire) une liste d'analyses
concises et actionnables, façon "executive briefing". Chaque insight a :

    title       Phrase courte (≤ 25 mots) avec un anchor numérique fort
    value       Métrique principale (string formaté)
    sub         Contexte / comparaison
    icon        Lucide icon
    tone        positive | neutral | warning | critical
    recommendation  Action concrète à prendre (≤ 15 mots)

Le LLM (si configuré) peut ensuite reformuler le résumé exécutif dans un
style plus narratif via `executive_summary()`.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


def _delta_pct(curr, prev):
    """Variation en % avec garde-fou contre la division par 0."""
    if not prev:
        return 100.0 if curr else 0.0
    return round((curr - prev) / prev * 100, 1)


def _format_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v} %"


def resolve_period(period: str = "week", start: str = "", end: str = ""):
    """Convertit un code période en (start_dt, end_dt, prev_start_dt, label).

    Codes : day, week, month, quarter, year, custom (utilise start/end ISO).
    """
    from datetime import date, datetime, timedelta
    now = timezone.now()
    today = now.date()
    if period == "day":
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now
        prev_start = start_dt - timedelta(days=1)
        prev_end = start_dt
        label = "aujourd'hui"
    elif period == "week":
        start_dt = now - timedelta(days=7)
        end_dt = now
        prev_start = now - timedelta(days=14)
        prev_end = start_dt
        label = "7 derniers jours"
    elif period == "month":
        start_dt = now - timedelta(days=30)
        end_dt = now
        prev_start = now - timedelta(days=60)
        prev_end = start_dt
        label = "30 derniers jours"
    elif period == "quarter":
        start_dt = now - timedelta(days=90)
        end_dt = now
        prev_start = now - timedelta(days=180)
        prev_end = start_dt
        label = "90 derniers jours"
    elif period == "year":
        start_dt = now - timedelta(days=365)
        end_dt = now
        prev_start = now - timedelta(days=730)
        prev_end = start_dt
        label = "365 derniers jours"
    elif period == "custom" and start and end:
        try:
            start_dt = timezone.make_aware(
                datetime.fromisoformat(start)) if "T" not in start else datetime.fromisoformat(start)
        except Exception:
            start_dt = now - timedelta(days=7)
        try:
            end_dt = timezone.make_aware(
                datetime.fromisoformat(end)) if "T" not in end else datetime.fromisoformat(end)
        except Exception:
            end_dt = now
        delta = end_dt - start_dt
        prev_start = start_dt - delta
        prev_end = start_dt
        label = f"{start_dt.date()} → {end_dt.date()}"
    else:
        # fallback
        start_dt = now - timedelta(days=7)
        end_dt = now
        prev_start = now - timedelta(days=14)
        prev_end = start_dt
        label = "7 derniers jours"
    return start_dt, end_dt, prev_start, prev_end, label


def compute_insights(period: str = "week", start: str = "", end: str = "") -> list[dict]:
    """Calcule la liste d'insights affichés sur /reports/.

    Période configurable : day | week | month | quarter | year | custom (start/end).

    Renvoie une liste vide si la DB n'est pas alimentée — l'UI affichera
    alors le bandeau "Insights indisponibles, lance seed_demo_data".
    """
    insights = []
    start_dt, end_dt, prev_start, prev_end, label = resolve_period(period, start, end)
    now = timezone.now()
    today = now.date()
    # Conserver les noms historiques pour ne pas casser le reste du code :
    week_ago = start_dt
    prev_week = prev_start

    try:
        from access_control.models import AccessEvent
        from antifraud.models import FraudAlert
        from devices.models import Badge
        from employees.models import Employee
        from ouvriers.models import Worker

        # ─── 1. Tendance scans période vs période précédente ──────
        scans_7d = AccessEvent.objects.filter(
            timestamp__gte=start_dt, timestamp__lte=end_dt).count()
        scans_prev_7d = AccessEvent.objects.filter(
            timestamp__gte=prev_start, timestamp__lt=prev_end).count()
        delta = _delta_pct(scans_7d, scans_prev_7d)
        if scans_7d == 0 and scans_prev_7d == 0:
            return []  # DB vide
        insights.append({
            "title": f"Activité d'accès en hausse de {_format_pct(delta)} sur {label}" if delta >= 0
                     else f"Activité d'accès en baisse de {_format_pct(delta)} sur {label}",
            "value": f"{scans_7d:,}".replace(",", " "),
            "sub": f"vs {scans_prev_7d:,} période précédente".replace(",", " "),
            "icon": "trending-up" if delta >= 0 else "trending-down",
            "tone": "positive" if -10 <= delta <= 30 else ("warning" if delta > 30 else "critical"),
            "recommendation": (
                "Anticiper la charge sur les terminaux IoT." if delta > 30
                else "Vérifier la cause de la baisse de fréquentation." if delta < -10
                else "Niveau d'activité stable, aucune action requise."
            ),
        })

        # ─── 2. Taux de refus du jour vs 7j ──────────────────────
        denied_today = AccessEvent.objects.filter(
            timestamp__date=today, decision="denied").count()
        total_today = AccessEvent.objects.filter(timestamp__date=today).count()
        denied_7d = AccessEvent.objects.filter(
            timestamp__gte=week_ago, decision="denied").count()
        total_7d = scans_7d or 1
        rate_today = round(denied_today / max(total_today, 1) * 100, 1)
        rate_avg = round(denied_7d / total_7d * 100, 1)
        delta_rate = round(rate_today - rate_avg, 1)
        insights.append({
            "title": (
                f"Taux de refus à {rate_today} % aujourd'hui "
                f"({_format_pct(delta_rate)} pt vs moyenne 7j)"
            ),
            "value": f"{rate_today} %",
            "sub": f"{denied_today} refus / {total_today} scans",
            "icon": "shield-x",
            "tone": "critical" if rate_today > rate_avg + 5 else
                    "warning" if rate_today > rate_avg + 2 else "positive",
            "recommendation": (
                "Auditer les motifs de refus dominants." if rate_today > rate_avg + 5
                else "Surveiller, taux nominal."
            ),
        })

        # ─── 3. Top site (charge) ──────────────────────────────────
        from django.db.models import Count
        top = (AccessEvent.objects
               .filter(timestamp__gte=week_ago, site__isnull=False)
               .values("site_id", "site__name")
               .annotate(c=Count("id"))
               .order_by("-c").first())
        if top:
            share = round(top["c"] / total_7d * 100, 1)
            insights.append({
                "title": (
                    f"{top['site__name']} concentre {share} % de l'activité hebdomadaire"
                ),
                "value": f"{top['c']:,}".replace(",", " "),
                "sub": f"scans cette semaine — {top['site__name']}",
                "icon": "map-pin",
                "tone": "warning" if share > 60 else "neutral",
                "recommendation": (
                    "Dimensionner les ressources sur ce site." if share > 60
                    else "Répartition acceptable des flux."
                ),
            })

        # ─── 4. Pic horaire ───────────────────────────────────────
        hour_buckets = Counter()
        for ev in AccessEvent.objects.filter(timestamp__gte=week_ago).only("timestamp"):
            hour_buckets[timezone.localtime(ev.timestamp).hour] += 1
        if hour_buckets:
            peak_hour, peak_count = hour_buckets.most_common(1)[0]
            insights.append({
                "title": (
                    f"Pic d'activité à {peak_hour:02d}h00 — "
                    f"{peak_count} scans en moyenne sur 7 jours"
                ),
                "value": f"{peak_hour:02d}h",
                "sub": f"{peak_count:,} scans cumulés".replace(",", " "),
                "icon": "clock",
                "tone": "neutral",
                "recommendation": "Renforcer la présence opérateur à cette tranche.",
            })

        # ─── 5. Alertes anti-fraude ──────────────────────────────
        alerts_open = FraudAlert.objects.filter(status="open").count()
        alerts_critical = FraudAlert.objects.filter(
            status="open", severity__in=("critical", "high")).count()
        insights.append({
            "title": (
                f"{alerts_open} alerte{'s' if alerts_open > 1 else ''} anti-fraude "
                f"ouverte{'s' if alerts_open > 1 else ''} dont {alerts_critical} critique"
                + ("s" if alerts_critical > 1 else "")
            ),
            "value": str(alerts_open),
            "sub": f"{alerts_critical} en sévérité élevée/critique",
            "icon": "shield-alert",
            "tone": "critical" if alerts_critical > 0 else (
                "warning" if alerts_open > 0 else "positive"),
            "recommendation": (
                "Acquitter ou escalader sans délai." if alerts_critical
                else "Triage à faire dans la journée." if alerts_open
                else "Aucune alerte en cours, RAS."
            ),
        })

        # ─── 6. Couverture badge ─────────────────────────────────
        emp_active = Employee.objects.filter(status="active").count() or 0
        wrk_active = Worker.objects.filter(status="active").count() or 0
        emp_badged = Badge.objects.filter(
            category="employee_rfid", status__in=("active", "assigned"),
            holder_kind="employee",
        ).values("holder_object_id").distinct().count()
        wrk_badged = Badge.objects.filter(
            category="worker_rfid", status__in=("active", "assigned"),
            holder_kind="worker",
        ).values("holder_object_id").distinct().count()
        total_pop = emp_active + wrk_active or 1
        total_badged = emp_badged + wrk_badged
        coverage = round(total_badged / total_pop * 100, 1)
        insights.append({
            "title": (
                f"Couverture badge : {coverage} % "
                f"({total_badged}/{total_pop} actifs équipés)"
            ),
            "value": f"{coverage} %",
            "sub": f"{emp_badged}/{emp_active} empl · {wrk_badged}/{wrk_active} ouvr",
            "icon": "badge-check",
            "tone": "positive" if coverage >= 90 else (
                "warning" if coverage >= 70 else "critical"),
            "recommendation": (
                "Émettre les badges manquants." if coverage < 90
                else "Couverture nominale."
            ),
        })

    except Exception:
        logger.exception("compute_insights failed")
        return []

    return insights


def compute_attendance_breakdown(period: str = "week", start: str = "", end: str = ""):
    """Calcule présence confirmée vs effectif attendu, ventilé par filiale et par site.

    "Présence confirmée" = nombre de personnes uniques (employee/worker)
    ayant au moins un AccessEvent decision=granted sur la période.
    "Effectif attendu" = personnes actives rattachées (Employee.company pour les
    employés, AccessEvent.holder_kind="worker" pour les ouvriers).

    Retourne :
        {
            "by_company": [{"name": ..., "expected_emp": N, "present_emp": M,
                            "expected_wrk": ..., "present_wrk": ...}, ...],
            "by_site": [...],
            "label": "7 derniers jours",
        }
    """
    out = {"by_company": [], "by_site": [], "label": ""}
    try:
        start_dt, end_dt, _, _, label = resolve_period(period, start, end)
        out["label"] = label

        from access_control.models import AccessEvent
        from core.models import Company
        from employees.models import Employee
        from ouvriers.models import Worker
        from sites.models import Site

        # ─── Personnes uniques ayant scanné dans la période ──────
        present_qs = (AccessEvent.objects
                      .filter(timestamp__gte=start_dt, timestamp__lte=end_dt,
                              decision="granted",
                              holder_object_id__isnull=False)
                      .values("holder_kind", "holder_object_id", "site_id"))
        # Map (kind, id) → set des site_ids
        present_by_holder = {}
        for row in present_qs:
            key = (row["holder_kind"], row["holder_object_id"])
            present_by_holder.setdefault(key, set()).add(row["site_id"])

        present_emp_ids = {hid for (k, hid) in present_by_holder if k == "employee"}
        present_wrk_ids = {hid for (k, hid) in present_by_holder if k == "worker"}

        # Présence par site = comptage holders distincts par site
        present_emp_by_site = {}
        present_wrk_by_site = {}
        for (kind, hid), sites in present_by_holder.items():
            for sid in sites:
                if not sid:
                    continue
                if kind == "employee":
                    present_emp_by_site.setdefault(sid, set()).add(hid)
                elif kind == "worker":
                    present_wrk_by_site.setdefault(sid, set()).add(hid)

        # ─── Ventilation par filiale ──────────────────────────────
        for c in Company.objects.filter(is_active=True).order_by("name"):
            emp_qs = Employee.objects.filter(company=c, status="active")
            expected_emp = emp_qs.count()
            present_emp = emp_qs.filter(id__in=present_emp_ids).count()

            sites_of_co = list(Site.objects.filter(
                company=c).values_list("id", flat=True))
            # Workers expected = personnes ayant déjà émis un AccessEvent worker
            # sur l'un des sites de la filiale (proxy de "rattachement")
            expected_wrk_qs = Worker.objects.filter(status="active")
            if sites_of_co:
                wrk_seen = set(AccessEvent.objects.filter(
                    site__in=sites_of_co, holder_kind="worker",
                ).values_list("holder_object_id", flat=True).distinct())
                expected_wrk_qs = expected_wrk_qs.filter(id__in=wrk_seen)
            else:
                expected_wrk_qs = expected_wrk_qs.none()
            expected_wrk = expected_wrk_qs.count()
            present_wrk = expected_wrk_qs.filter(id__in=present_wrk_ids).count()

            rate_emp = round(present_emp / expected_emp * 100, 1) if expected_emp else 0
            rate_wrk = round(present_wrk / expected_wrk * 100, 1) if expected_wrk else 0
            total_expected = expected_emp + expected_wrk
            total_present = present_emp + present_wrk
            rate_total = round(total_present / total_expected * 100, 1) if total_expected else 0

            out["by_company"].append({
                "id": c.id, "name": c.name, "code": c.code,
                "logo": c.logo.url if c.logo else "",
                "expected_emp": expected_emp, "present_emp": present_emp, "rate_emp": rate_emp,
                "expected_wrk": expected_wrk, "present_wrk": present_wrk, "rate_wrk": rate_wrk,
                "total_expected": total_expected, "total_present": total_present,
                "rate_total": rate_total,
            })

        # ─── Ventilation par site ──────────────────────────────────
        for s in Site.objects.select_related("company").filter(
                status="active").order_by("name"):
            present_emp = len(present_emp_by_site.get(s.id, set()))
            present_wrk = len(present_wrk_by_site.get(s.id, set()))
            expected_emp = Employee.objects.filter(
                company=s.company, status="active",
                authorized_sites=s,
            ).count() if s.company else 0
            # Fallback : si aucun employé n'a authorized_sites pour ce site,
            # on utilise les employés présents comme attendus (pas idéal mais évite 0/0)
            if not expected_emp:
                expected_emp = max(
                    present_emp,
                    Employee.objects.filter(
                        company=s.company, status="active",
                    ).count() if s.company else 0,
                )
            expected_wrk = AccessEvent.objects.filter(
                site=s, holder_kind="worker",
            ).values("holder_object_id").distinct().count()

            total_e = expected_emp + expected_wrk
            total_p = present_emp + present_wrk
            rate = round(total_p / total_e * 100, 1) if total_e else 0
            out["by_site"].append({
                "id": s.id, "name": s.name, "code": s.code,
                "company": s.company.name if s.company else "—",
                "type": s.get_type_display(),
                "expected_emp": expected_emp, "present_emp": present_emp,
                "expected_wrk": expected_wrk, "present_wrk": present_wrk,
                "total_expected": total_e, "total_present": total_p,
                "rate": rate,
            })

    except Exception:
        logger.exception("compute_attendance_breakdown failed")
    return out


def executive_summary(insights: list[dict]) -> str:
    """Synthétise les 6 insights en 2-3 phrases via LLM (si dispo) ou fallback.

    Le résultat est toujours produit — fallback déterministe quand le LLM
    n'est pas configuré. Limité à ~280 caractères pour rester punchy.
    """
    if not insights:
        return ""

    # Fallback déterministe — concatène les titres les plus saillants
    critical = [i for i in insights if i["tone"] == "critical"]
    warning = [i for i in insights if i["tone"] == "warning"]
    fallback = ""
    if critical:
        fallback = "Points critiques : " + " · ".join(
            i["title"] for i in critical[:2])
    elif warning:
        fallback = "Vigilance : " + " · ".join(
            i["title"] for i in warning[:2])
    else:
        fallback = (
            f"Activité nominale : {insights[0]['title'].split(' ')[0:6]} "
            "— aucune anomalie significative."
        )
        fallback = " ".join(insights[0]["title"].split()[:8]).rstrip(".") + "."

    # Si LLM dispo, on demande une reformulation concise
    try:
        from django.conf import settings
        api_key = settings.KAYDAN_SHIELD.get("OPENAI_API_KEY")
        if not api_key:
            return fallback

        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        bullets = "\n".join(
            f"- [{i['tone']}] {i['title']} ({i['value']})"
            for i in insights
        )
        prompt = (
            "Voici 6 indicateurs métier d'une plateforme de contrôle d'accès. "
            "Rédige un résumé exécutif en 2 phrases maximum (≤ 280 caractères), "
            "en français, qui met en avant les points d'attention. "
            "Sois actionnable et factuel.\n\n" + bullets
        )
        resp = client.chat.completions.create(
            model=settings.KAYDAN_SHIELD.get("AI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=180,
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text[:300] if text else fallback
    except Exception:
        logger.debug("LLM fallback used", exc_info=True)
        return fallback
