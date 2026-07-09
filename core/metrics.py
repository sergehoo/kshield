"""KAYDAN SHIELD — Métriques Prometheus business.

En plus des métriques techniques fournies par django-prometheus (latence
HTTP, queries DB, cache), on expose des compteurs et gauges métier qu'on
incrémente depuis les services :

    from core.metrics import scans_total, fraud_alerts_open

    scans_total.labels(decision="granted", site="HQ").inc()
    fraud_alerts_open.labels(severity="critical").set(qs.count())

Endpoint exporter : GET /metrics (configuré dans urls.py).
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ─── Compteurs (incréments à chaque événement) ─────────────────────────
scans_total = Counter(
    "kshield_scans_total",
    "Nombre total de scans badge traités.",
    ["decision", "method", "site"],  # granted/denied/review × nfc/uhf/qr × site_code
)

fraud_alerts_raised = Counter(
    "kshield_fraud_alerts_raised_total",
    "Nombre total d'alertes anti-fraude levées.",
    ["rule_code", "severity"],
)

face_matches_total = Counter(
    "kshield_face_matches_total",
    "Nombre de matches face recognition (engine = client | insightface).",
    ["engine", "result"],  # result = matched | unmatched
)

camera_stream_clients = Counter(
    "kshield_camera_stream_clients_total",
    "Connexions MJPEG ouvertes (cumulatif).",
    ["camera_id"],
)

sync_offline_push = Counter(
    "kshield_sync_offline_push_total",
    "Scans bufferisés poussés depuis une gateway offline.",
    ["device_id", "result"],  # result = synced | duplicate | rejected
)

# ─── Enrôlement RFID temps réel ────────────────────────────────────────
rfid_scans_total = Counter(
    "kshield_rfid_scans_total",
    "Scans RFID captés pendant les sessions d'enrôlement.",
    ["result"],   # detected | duplicate | enrolled | error
)

enrollment_sessions_total = Counter(
    "kshield_enrollment_sessions_total",
    "Sessions d'enrôlement RFID démarrées / clôturées.",
    ["outcome"],   # started | completed | cancelled | timeout
)

device_commands_total = Counter(
    "kshield_device_commands_total",
    "Commandes envoyées aux équipements.",
    ["kind", "status"],  # PING_DEVICE, SYNC_DEVICE, ... × sent/completed/failed/timeout
)

local_agents_connected = Gauge(
    "kshield_local_agents_connected",
    "Nombre d'agents locaux actuellement connectés en WebSocket.",
)

# ─── Gauges (valeurs instantanées, snapshot temps réel) ───────────────
fraud_alerts_open = Gauge(
    "kshield_fraud_alerts_open",
    "Nombre d'alertes anti-fraude actuellement ouvertes (par sévérité).",
    ["severity"],
)

devices_online = Gauge(
    "kshield_devices_online",
    "Nombre de terminaux IoT en ligne (heartbeat < 90s).",
    ["device_type"],
)

cameras_online = Gauge(
    "kshield_cameras_online",
    "Nombre de caméras IP en ligne.",
)

helmets_active = Gauge(
    "kshield_helmets_active",
    "Nombre de casques BLE émettant un beacon récent.",
)

visitors_on_site = Gauge(
    "kshield_visitors_on_site",
    "Nombre de visiteurs actuellement présents sur site.",
    ["site"],
)

# ─── Histogrammes (distributions de durées/scores) ────────────────────
scan_processing_seconds = Histogram(
    "kshield_scan_processing_seconds",
    "Durée du process_scan() de bout-en-bout.",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0),
)

face_match_score = Histogram(
    "kshield_face_match_score",
    "Distribution des scores cosine des matches faciaux.",
    buckets=(0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)


# ─── Updater pour gauges (à appeler périodiquement) ───────────────────
def refresh_gauges():
    """Met à jour toutes les gauges depuis l'état courant de la DB.

    À appeler depuis une task Celery (toutes les 30s) ou en sync depuis
    une vue admin. Idempotent.
    """
    try:
        from antifraud.models import FraudAlert
        for sev in ("info", "warning", "critical"):
            n = FraudAlert.objects.filter(status="open", severity=sev).count()
            fraud_alerts_open.labels(severity=sev).set(n)
    except Exception:
        pass

    try:
        from datetime import timedelta
        from django.utils import timezone
        from devices.models import Device, Camera, Helmet
        cutoff = timezone.now() - timedelta(seconds=90)
        for dtype in ("reader_nfc_fixed", "reader_uhf_fixed", "tablet", "camera"):
            n = Device.objects.filter(
                model__type=dtype, last_heartbeat_at__gte=cutoff,
            ).count()
            devices_online.labels(device_type=dtype).set(n)

        cameras_online.set(Camera.objects.filter(status="online").count())

        helmet_cutoff = timezone.now() - timedelta(minutes=5)
        helmets_active.set(
            Helmet.objects.filter(last_seen_at__gte=helmet_cutoff).count()
        )
    except Exception:
        pass

    try:
        from visitors.models import VisitRequest
        rows = (VisitRequest.objects.filter(status="checked_in")
                .values("site__code")
                .order_by())
        for r in rows:
            visitors_on_site.labels(site=r["site__code"] or "unknown").set(1)
    except Exception:
        pass
