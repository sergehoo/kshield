"""KAYDAN SHIELD — Service génération Digest exécutif IA (hebdo/mensuel).

Pipeline :

    1. compute_period_metrics(tenant, period_start, period_end)
       ─ Agrège les KPI (scans, alertes, présence, anomalies) sur la période.

    2. generate_digest(digest)
       ─ Appelle le LLM (OpenAI / fallback heuristique) pour produire :
           · title         (≤ 120 chars)
           · executive_summary    (2-3 paragraphes)
           · top_alerts          (top 5)
           · kpi_deltas          (variations %)
           · anomalies           (patterns inhabituels)
           · recommendations     (3-5 actions)

    3. send_digest_email(digest, recipients=None)
       ─ Rend le HTML/texte et l'envoie via `notifications.services` ou
         `django.core.mail.send_mail` aux abonnés configurés.

Robustesse :
  · Toute opération est try/except — le digest passe en status "failed" plutôt
    que de remonter une exception non gérée à Celery.
  · Si OPENAI_API_KEY absent, fallback déterministe (titres + bullets calculés).
  · Idempotence : la tâche réutilise un ExecutiveDigest existant pour
    (tenant, period, period_start) plutôt que d'en créer un doublon.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Période — helpers
# ---------------------------------------------------------------------------
def resolve_digest_period(period: str = "weekly",
                          anchor: Optional[date] = None) -> tuple[date, date]:
    """Retourne (period_start, period_end) pour le digest.

    Le lundi 00:00 → dimanche 23:59 pour 'weekly', etc. `anchor` est la date
    de référence à laquelle on attache la période (par défaut today - 1 jour
    pour générer le digest pour la *semaine qui vient de s'écouler*).
    """
    today = anchor or timezone.now().date()
    if period == "weekly":
        # Lundi de la semaine PRÉCÉDENTE → dimanche
        weekday = today.weekday()  # lundi=0, dimanche=6
        last_monday = today - timedelta(days=weekday + 7)
        last_sunday = last_monday + timedelta(days=6)
        return last_monday, last_sunday
    if period == "monthly":
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end
    if period == "quarterly":
        # Trimestre précédent
        q_idx = (today.month - 1) // 3  # 0..3 pour Q1..Q4
        if q_idx == 0:
            start = date(today.year - 1, 10, 1)
            end = date(today.year - 1, 12, 31)
        else:
            start_month = (q_idx - 1) * 3 + 1
            start = date(today.year, start_month, 1)
            # fin = veille du début du trimestre courant
            cur_start_month = q_idx * 3 + 1
            end = date(today.year, cur_start_month, 1) - timedelta(days=1)
        return start, end
    # défaut weekly
    return resolve_digest_period("weekly", anchor)


# ---------------------------------------------------------------------------
# KPI : agrégation pour la période
# ---------------------------------------------------------------------------
def compute_period_metrics(tenant, period_start: date, period_end: date) -> dict:
    """Calcule les métriques nécessaires au digest.

    Retourne un dict structuré, sérialisable JSON, contenant toutes les
    données utiles pour : LLM prompt, fallback texte, email HTML, UI admin.

    Format :
        {
          "scans": {
            "total": int, "granted": int, "denied": int, "denial_rate": float,
            "by_decision": {decision: count},
            "by_site": [{"site": ..., "count": ...}],
            "trend_vs_prev_pct": float,
          },
          "alerts": {
            "total": int, "open": int, "critical": int,
            "by_severity": {severity: count},
            "top": [{"rule": ..., "severity": ..., "site": ..., "ts": ...}],
          },
          "attendance": {
            "punches_total": int, "unique_workers": int, "unique_employees": int,
            "presence_rate": float, "avg_delay_min": float,
          },
          "visitors": {
            "total": int, "approved": int, "rejected": int, "checked_in": int,
          },
          "anomalies": [...],
        }
    """
    from datetime import datetime as _dt

    start_dt = timezone.make_aware(_dt.combine(period_start, _dt.min.time()))
    end_dt = timezone.make_aware(_dt.combine(period_end, _dt.max.time()))
    prev_start = start_dt - (end_dt - start_dt) - timedelta(seconds=1)
    prev_end = start_dt - timedelta(seconds=1)

    out = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "tenant_id": tenant.id if tenant else None,
        "scans": {}, "alerts": {}, "attendance": {},
        "visitors": {}, "anomalies": [],
    }

    # ─── Scans / accès ─────────────────────────────────────────────────
    try:
        from access_control.models import AccessEvent
        from django.db.models import Count

        qs = AccessEvent.objects.filter(timestamp__gte=start_dt,
                                          timestamp__lte=end_dt)
        if tenant:
            qs = qs.filter(tenant=tenant)
        total = qs.count()
        granted = qs.filter(decision="granted").count()
        denied = qs.filter(decision="denied").count()

        by_decision = dict(qs.values("decision").annotate(c=Count("id"))
                              .values_list("decision", "c"))
        top_sites = list(qs.filter(site__isnull=False)
                         .values("site_id", "site__name")
                         .annotate(c=Count("id")).order_by("-c")[:5])

        prev_qs = AccessEvent.objects.filter(timestamp__gte=prev_start,
                                              timestamp__lt=start_dt)
        if tenant:
            prev_qs = prev_qs.filter(tenant=tenant)
        prev_total = prev_qs.count()
        delta_pct = ((total - prev_total) / prev_total * 100) if prev_total else \
                    (100.0 if total else 0.0)

        out["scans"] = {
            "total": total,
            "granted": granted,
            "denied": denied,
            "denial_rate": round(denied / total * 100, 1) if total else 0.0,
            "by_decision": by_decision,
            "by_site": [{"site_id": s["site_id"], "site": s["site__name"],
                          "count": s["c"]} for s in top_sites],
            "previous_total": prev_total,
            "trend_vs_prev_pct": round(delta_pct, 1),
        }
    except Exception:
        logger.warning("digest.compute: scans agrégation impossible",
                       exc_info=True)

    # ─── Alertes anti-fraude ───────────────────────────────────────────
    try:
        from antifraud.models import FraudAlert
        from django.db.models import Count

        a_qs = FraudAlert.objects.filter(created_at__gte=start_dt,
                                          created_at__lte=end_dt)
        if tenant:
            a_qs = a_qs.filter(tenant=tenant)
        total_a = a_qs.count()
        open_a = a_qs.filter(status="open").count()
        critical_a = a_qs.filter(severity__in=("critical", "high")).count()
        by_sev = dict(a_qs.values("severity").annotate(c=Count("id"))
                          .values_list("severity", "c"))

        top_alerts = []
        for a in a_qs.select_related("rule", "site").order_by(
                "-severity", "-created_at")[:5]:
            top_alerts.append({
                "id": a.id,
                "rule": a.rule.name if a.rule_id else "—",
                "rule_code": a.rule.code if a.rule_id else "",
                "severity": a.severity,
                "site": a.site.name if a.site_id else "—",
                "ts": a.created_at.isoformat() if a.created_at else "",
                "status": a.status,
                "holder": f"{a.primary_holder_kind} #{a.primary_holder_id}"
                           if a.primary_holder_id else "—",
            })

        out["alerts"] = {
            "total": total_a, "open": open_a, "critical": critical_a,
            "by_severity": by_sev, "top": top_alerts,
        }
    except Exception:
        logger.warning("digest.compute: alertes agrégation impossible",
                       exc_info=True)

    # ─── Présence ──────────────────────────────────────────────────────
    try:
        from attendance.models import Punch

        p_qs = Punch.objects.filter(timestamp__gte=start_dt,
                                     timestamp__lte=end_dt)
        if tenant:
            p_qs = p_qs.filter(tenant=tenant)
        total_p = p_qs.count()
        emp_uniq = p_qs.filter(holder_kind="employee").values(
            "holder_object_id").distinct().count()
        wrk_uniq = p_qs.filter(holder_kind="worker").values(
            "holder_object_id").distinct().count()

        out["attendance"] = {
            "punches_total": total_p,
            "unique_employees": emp_uniq,
            "unique_workers": wrk_uniq,
        }
    except Exception:
        logger.debug("digest.compute: attendance agrégation impossible",
                     exc_info=True)

    # ─── Visiteurs ─────────────────────────────────────────────────────
    try:
        from visitors.models import VisitRequest

        v_qs = VisitRequest.objects.filter(created_at__gte=start_dt,
                                             created_at__lte=end_dt)
        if tenant:
            v_qs = v_qs.filter(tenant=tenant)
        out["visitors"] = {
            "total": v_qs.count(),
            "approved": v_qs.filter(status="approved").count(),
            "rejected": v_qs.filter(status="rejected").count(),
            "checked_in": v_qs.filter(status="checked_in").count(),
        }
    except Exception:
        logger.debug("digest.compute: visiteurs agrégation impossible",
                     exc_info=True)

    # ─── Anomalies heuristiques ────────────────────────────────────────
    anomalies = []
    try:
        scans = out.get("scans", {}) or {}
        if scans.get("denial_rate", 0) > 12:
            anomalies.append({
                "kind": "denial_spike",
                "label": f"Taux de refus élevé ({scans['denial_rate']} %)",
                "severity": "high",
            })
        if scans.get("trend_vs_prev_pct", 0) > 50:
            anomalies.append({
                "kind": "scan_surge",
                "label": f"Activité en hausse de {scans['trend_vs_prev_pct']} %",
                "severity": "medium",
            })
        elif scans.get("trend_vs_prev_pct", 0) < -25:
            anomalies.append({
                "kind": "scan_drop",
                "label": f"Activité en baisse de {abs(scans['trend_vs_prev_pct'])} %",
                "severity": "high",
            })
        alerts = out.get("alerts", {}) or {}
        if alerts.get("critical", 0) >= 3:
            anomalies.append({
                "kind": "critical_alerts",
                "label": f"{alerts['critical']} alertes critiques/hautes",
                "severity": "critical",
            })
    except Exception:
        logger.debug("digest.compute: heuristiques anomalies",
                     exc_info=True)
    out["anomalies"] = anomalies
    return out


# ---------------------------------------------------------------------------
# Génération LLM
# ---------------------------------------------------------------------------
_FALLBACK_PROMPT_NOTE = (
    "[Mode dégradé — synthèse heuristique, configurez OPENAI_API_KEY pour "
    "un résumé rédigé par le LLM.]"
)


def _build_prompt(metrics: dict, period_label: str) -> str:
    """Construit le prompt LLM en français à partir des métriques."""
    s = metrics.get("scans", {}) or {}
    a = metrics.get("alerts", {}) or {}
    att = metrics.get("attendance", {}) or {}
    v = metrics.get("visitors", {}) or {}

    top_alerts_block = "\n".join(
        f"  · [{x.get('severity', '—').upper()}] {x.get('rule', '—')} "
        f"sur {x.get('site', '—')} ({x.get('ts', '')[:16]})"
        for x in (a.get("top") or [])
    ) or "  · Aucune alerte top à signaler."

    sites_block = ", ".join(
        f"{x.get('site', '—')} ({x.get('count', 0)})"
        for x in (s.get("by_site") or [])
    ) or "—"

    return (
        f"Tu es l'analyste sécurité senior de KAYDAN GROUPE. Rédige le "
        f"digest exécutif {period_label} destiné au CEO/COO.\n\n"
        f"DONNÉES BRUTES :\n"
        f"- Scans : {s.get('total', 0)} (Granted {s.get('granted', 0)} / "
        f"Denied {s.get('denied', 0)}, taux refus {s.get('denial_rate', 0)} %)\n"
        f"- Tendance vs période précédente : {s.get('trend_vs_prev_pct', 0)} %\n"
        f"- Top sites : {sites_block}\n"
        f"- Alertes anti-fraude : {a.get('total', 0)} (dont {a.get('critical', 0)} "
        f"critiques/hautes, {a.get('open', 0)} ouvertes)\n"
        f"- Top alertes :\n{top_alerts_block}\n"
        f"- Pointage : {att.get('punches_total', 0)} punches, "
        f"{att.get('unique_employees', 0)} employés uniques, "
        f"{att.get('unique_workers', 0)} ouvriers uniques\n"
        f"- Visiteurs : {v.get('total', 0)} demandes ({v.get('approved', 0)} appr., "
        f"{v.get('rejected', 0)} ref., {v.get('checked_in', 0)} arrivés)\n\n"
        f"CONSIGNES — Réponds **uniquement** en JSON strict avec ce schéma :\n"
        f'{{\n'
        f'  "title": "string ≤ 120 chars, factuel et accrocheur",\n'
        f'  "executive_summary": "2 paragraphes (≤ 600 chars) — vue d\'ensemble + 1 action prio",\n'
        f'  "kpi_deltas": [{{"label": "...", "value": "...", "trend": "up|down|flat", "comment": "..."}}],\n'
        f'  "anomalies": [{{"label": "...", "severity": "low|medium|high|critical", "evidence": "..."}}],\n'
        f'  "recommendations": [{{"title": "...", "action": "...", "owner": "..."}}]\n'
        f'}}\n'
        f"Sois concret, chiffré, sans bla-bla. 3 à 5 recommandations max."
    )


def _call_openai(prompt: str, model: str) -> tuple[str, int, float]:
    """Appel OpenAI Chat Completions. Retourne (texte, tokens_used, seconds)."""
    api_key = settings.KAYDAN_SHIELD.get("OPENAI_API_KEY")
    if not api_key:
        return "", 0, 0.0

    t0 = time.time()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",
                 "content": "Tu es un analyste data senior, francophone, "
                             "factuel. Réponds uniquement en JSON valide."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        text = (resp.choices[0].message.content or "").strip()
        tokens = getattr(resp.usage, "total_tokens", 0) if resp.usage else 0
        return text, tokens, round(time.time() - t0, 2)
    except Exception as exc:
        logger.warning("digest LLM call failed: %s", exc, exc_info=True)
        return "", 0, round(time.time() - t0, 2)


def _heuristic_digest(metrics: dict, period_label: str) -> dict:
    """Fallback déterministe si LLM indisponible."""
    s = metrics.get("scans", {}) or {}
    a = metrics.get("alerts", {}) or {}
    att = metrics.get("attendance", {}) or {}
    v = metrics.get("visitors", {}) or {}

    deltas = []
    if s:
        trend = s.get("trend_vs_prev_pct", 0)
        deltas.append({
            "label": "Volume de scans", "value": f"{s.get('total', 0)}",
            "trend": "up" if trend >= 0 else "down",
            "comment": f"{trend:+.1f} % vs période précédente",
        })
        deltas.append({
            "label": "Taux de refus", "value": f"{s.get('denial_rate', 0)} %",
            "trend": "up" if s.get('denial_rate', 0) > 10 else "flat",
            "comment": f"{s.get('denied', 0)} refus / {s.get('total', 0)} scans",
        })
    if a:
        deltas.append({
            "label": "Alertes anti-fraude", "value": str(a.get("total", 0)),
            "trend": "up" if a.get("critical", 0) else "flat",
            "comment": f"{a.get('critical', 0)} critiques/hautes",
        })
    if v.get("total"):
        deltas.append({
            "label": "Demandes de visite", "value": str(v["total"]),
            "trend": "flat",
            "comment": f"{v.get('approved', 0)} approuvées · "
                       f"{v.get('checked_in', 0)} arrivées",
        })

    title = (f"Digest {period_label} — "
             f"{s.get('total', 0)} scans · {a.get('total', 0)} alertes")

    parts = []
    parts.append(
        f"Sur la période, {s.get('total', 0)} accès ont été contrôlés "
        f"({s.get('granted', 0)} accordés, {s.get('denied', 0)} refusés, "
        f"soit {s.get('denial_rate', 0)} % de refus). "
        f"Tendance : {s.get('trend_vs_prev_pct', 0):+.1f} % vs période précédente."
    )
    parts.append(
        f"{a.get('total', 0)} alerte(s) anti-fraude levée(s), "
        f"dont {a.get('critical', 0)} critique(s). "
        f"{att.get('punches_total', 0)} pointages enregistrés sur "
        f"{att.get('unique_workers', 0)} ouvriers et "
        f"{att.get('unique_employees', 0)} employés uniques."
    )
    summary = " ".join(parts) + " " + _FALLBACK_PROMPT_NOTE

    recos = []
    if a.get("critical", 0):
        recos.append({
            "title": "Triage des alertes critiques",
            "action": "Acquitter ou escalader les alertes sévérité haute/critique "
                      "ouvertes dans les 24h.",
            "owner": "Responsable sécurité",
        })
    if s.get("denial_rate", 0) > 10:
        recos.append({
            "title": "Auditer les motifs de refus",
            "action": "Extraire les top denial_reason et corriger les badges/règles.",
            "owner": "Admin contrôle d'accès",
        })
    if s.get("trend_vs_prev_pct", 0) > 30:
        recos.append({
            "title": "Anticiper la charge IoT",
            "action": "Vérifier la santé des terminaux et la latence Redis.",
            "owner": "Ops",
        })
    if v.get("rejected", 0) > 5:
        recos.append({
            "title": "Revoir les invitations visiteurs",
            "action": "Communiquer aux hôtes les critères d'acceptation.",
            "owner": "Accueil / Sûreté",
        })
    if not recos:
        recos.append({
            "title": "Maintien du dispositif",
            "action": "Aucune anomalie significative — poursuivre la routine "
                      "de supervision.",
            "owner": "Centre opérationnel",
        })

    return {
        "title": title[:240],
        "executive_summary": summary,
        "kpi_deltas": deltas,
        "anomalies": metrics.get("anomalies", []),
        "recommendations": recos,
        "top_alerts": (a.get("top") or [])[:5],
    }


def generate_digest(digest) -> bool:
    """Génère (ou régénère) le contenu d'un ExecutiveDigest.

    Met à jour `digest` en place et le sauve. Retourne True si OK.
    """
    digest.status = "generating"
    digest.error_message = ""
    digest.save(update_fields=["status", "error_message", "updated_at"])

    period_label = {
        "weekly": "hebdomadaire",
        "monthly": "mensuel",
        "quarterly": "trimestriel",
    }.get(digest.period, "hebdomadaire")

    t0 = time.time()
    try:
        metrics = compute_period_metrics(
            digest.tenant, digest.period_start, digest.period_end)
        digest.raw_metrics = metrics

        # ── Tentative LLM ────────────────────────────────────────────
        prompt = _build_prompt(metrics, period_label)
        model = settings.KAYDAN_SHIELD.get("AI_MODEL", "gpt-4o-mini")
        text, tokens, seconds = _call_openai(prompt, model)

        payload = None
        if text:
            try:
                payload = json.loads(text)
                digest.model_used = model
                digest.tokens_used = tokens
            except json.JSONDecodeError:
                logger.warning("Digest LLM a renvoyé du JSON invalide, "
                               "fallback heuristique")
                payload = None

        if not payload:
            payload = _heuristic_digest(metrics, period_label)
            digest.model_used = digest.model_used or "heuristic"

        digest.title = (payload.get("title") or
                         f"Digest {period_label} — "
                         f"{digest.period_start:%d/%m} → "
                         f"{digest.period_end:%d/%m}")[:240]
        digest.executive_summary = payload.get("executive_summary", "")[:4000]
        digest.kpi_deltas = payload.get("kpi_deltas", []) or []
        digest.anomalies = (payload.get("anomalies") or
                             metrics.get("anomalies", []))
        digest.recommendations = payload.get("recommendations", []) or []
        # top_alerts toujours issu des métriques fiables, pas du LLM
        digest.top_alerts = (metrics.get("alerts", {}) or {}).get("top", [])[:5]

        digest.generation_seconds = round(time.time() - t0, 2)
        digest.status = "ready"
        digest.save()
        return True
    except Exception as exc:
        logger.exception("generate_digest failed for digest=%s", digest.id)
        digest.status = "failed"
        digest.error_message = str(exc)[:500]
        digest.generation_seconds = round(time.time() - t0, 2)
        digest.save(update_fields=[
            "status", "error_message", "generation_seconds", "updated_at",
        ])
        return False


# ---------------------------------------------------------------------------
# Diffusion email
# ---------------------------------------------------------------------------
def _resolve_digest_recipients(tenant) -> list[str]:
    """Retourne la liste d'emails à notifier pour ce tenant.

    Stratégie : staff actifs + utilisateurs avec permission `reports.view_executivedigest`.
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        qs = User.objects.filter(is_active=True, email__isnull=False).exclude(email="")
        emails = list(qs.filter(is_staff=True).values_list("email", flat=True).distinct())
        return [e for e in emails if e]
    except Exception:
        logger.warning("digest recipients resolution failed", exc_info=True)
        return []


def _render_digest_html(digest) -> tuple[str, str]:
    """Rend le digest en (subject, html_body) simple, sans dépendance externe."""
    subject = f"[KAYDAN SHIELD] {digest.title}"

    def _row(label, value):
        return (f"<tr><td style='padding:6px 12px;color:#94a3b8'>{label}</td>"
                f"<td style='padding:6px 12px;font-weight:600'>{value}</td></tr>")

    deltas_html = "".join(
        _row(d.get("label", "—"),
             f"{d.get('value', '—')} <span style='color:#64748b'>"
             f"({d.get('comment', '')})</span>")
        for d in (digest.kpi_deltas or [])
    )

    alerts_html = "".join(
        f"<li><strong>[{x.get('severity', '—').upper()}]</strong> "
        f"{x.get('rule', '—')} — {x.get('site', '—')} "
        f"<span style='color:#64748b'>({(x.get('ts') or '')[:16]})</span></li>"
        for x in (digest.top_alerts or [])
    )

    recos_html = "".join(
        f"<li><strong>{r.get('title', '—')}</strong> — "
        f"{r.get('action', '')} "
        f"<em style='color:#64748b'>({r.get('owner', '')})</em></li>"
        for r in (digest.recommendations or [])
    )

    anomalies_html = "".join(
        f"<li><strong>[{a.get('severity', '—').upper()}]</strong> "
        f"{a.get('label', '—')}</li>"
        for a in (digest.anomalies or [])
    )

    html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;
                max-width:680px;margin:0 auto;color:#0f172a;line-height:1.55">
      <div style="background:linear-gradient(135deg,#f26b1f,#d946ef);
                  padding:24px;border-radius:14px 14px 0 0;color:white">
        <div style="opacity:.85;font-size:12px;text-transform:uppercase;
                    letter-spacing:.08em">KAYDAN SHIELD — Digest exécutif</div>
        <h1 style="margin:8px 0 0;font-size:22px">{digest.title}</h1>
        <div style="opacity:.9;font-size:13px;margin-top:6px">
          Période : {digest.period_start:%d %b %Y} → {digest.period_end:%d %b %Y}
        </div>
      </div>
      <div style="background:white;border:1px solid #e2e8f0;border-top:0;
                  padding:20px 24px;border-radius:0 0 14px 14px">
        <p style="font-size:14px;color:#334155;white-space:pre-line">
{digest.executive_summary}
        </p>

        <h3 style="margin:18px 0 6px;font-size:14px;color:#0f172a">
          Indicateurs clés
        </h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;
                       background:#f8fafc;border-radius:8px;overflow:hidden">
          {deltas_html or '<tr><td style="padding:8px">—</td></tr>'}
        </table>

        {f'<h3 style="margin:18px 0 6px;font-size:14px">Top alertes</h3>'
          f'<ul style="font-size:13px;padding-left:18px">{alerts_html}</ul>'
          if alerts_html else ''}

        {f'<h3 style="margin:18px 0 6px;font-size:14px">Anomalies détectées</h3>'
          f'<ul style="font-size:13px;padding-left:18px">{anomalies_html}</ul>'
          if anomalies_html else ''}

        <h3 style="margin:18px 0 6px;font-size:14px">Recommandations</h3>
        <ul style="font-size:13px;padding-left:18px">
          {recos_html or '<li>Aucune action particulière requise.</li>'}
        </ul>

        <div style="margin-top:20px;padding-top:14px;border-top:1px solid #e2e8f0;
                    font-size:11px;color:#94a3b8">
          Généré le {digest.updated_at:%d/%m/%Y %H:%M} —
          modèle {digest.model_used or 'heuristic'}
          {f'· {digest.tokens_used} tokens' if digest.tokens_used else ''}
          · {digest.generation_seconds:.1f} s.
        </div>
      </div>
    </div>
    """.strip()

    return subject, html


def send_digest_email(digest, recipients: Optional[list[str]] = None) -> int:
    """Envoie le digest par email aux destinataires. Retourne le nombre envoyé."""
    if digest.status != "ready":
        logger.info("send_digest_email skipped: digest.status=%s", digest.status)
        return 0

    if recipients is None:
        recipients = _resolve_digest_recipients(digest.tenant)
    recipients = [r for r in (recipients or []) if r]
    if not recipients:
        logger.info("send_digest_email: aucun destinataire")
        return 0

    subject, html = _render_digest_html(digest)
    # Texte plain : strip tags rudimentaire
    import re
    plain = re.sub(r"<[^>]+>", "", html)
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()

    sent = 0
    try:
        send_mail(
            subject=subject,
            message=plain,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL",
                                 "no-reply@kaydangroupe.com"),
            recipient_list=recipients,
            html_message=html,
            fail_silently=False,
        )
        sent = len(recipients)
    except Exception as exc:
        logger.exception("send_digest_email failed: %s", exc)
        return 0

    digest.sent_at = timezone.now()
    digest.sent_to = recipients
    digest.save(update_fields=["sent_at", "sent_to", "updated_at"])
    return sent


# ---------------------------------------------------------------------------
# Orchestration — entrée principale
# ---------------------------------------------------------------------------
def get_or_create_digest(tenant, period: str = "weekly",
                         anchor: Optional[date] = None):
    """Idempotent : retourne le digest existant pour (tenant, period, start)
    ou en crée un nouveau en status 'queued'."""
    from .models import ExecutiveDigest
    period_start, period_end = resolve_digest_period(period, anchor)
    digest, _ = ExecutiveDigest.objects.get_or_create(
        tenant=tenant, period=period, period_start=period_start,
        defaults={"period_end": period_end, "status": "queued"},
    )
    # Si quelqu'un a corrompu period_end côté DB, on le réaligne
    if digest.period_end != period_end:
        digest.period_end = period_end
        digest.save(update_fields=["period_end", "updated_at"])
    return digest


def run_digest_pipeline(tenant, period: str = "weekly",
                         anchor: Optional[date] = None,
                         send_email: bool = True) -> dict:
    """Pipeline complet : crée/maj le digest, génère contenu, envoie email.

    Retourne un dict de résumé exécution.
    """
    digest = get_or_create_digest(tenant, period=period, anchor=anchor)
    ok = generate_digest(digest)
    sent = 0
    if ok and send_email:
        try:
            sent = send_digest_email(digest)
        except Exception:
            logger.exception("send_digest_email crash")
            sent = 0
    return {
        "digest_id": digest.id,
        "status": digest.status,
        "tokens_used": digest.tokens_used,
        "generation_seconds": digest.generation_seconds,
        "sent_to": sent,
        "title": digest.title,
    }
