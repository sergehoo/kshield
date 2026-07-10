"""KAYDAN SHIELD — Celery tasks temps réel (Vague 3).

Trois tâches périodiques :

    devices.sweep_command_timeouts   → toutes les 30s
    devices.reconcile_status         → toutes les 60s
    devices.sweep_stale_agents       → toutes les heures

Elles complètent la stack Communication temps réel :
  * Détectent les commandes qui n'ont jamais été acquittées
  * Passent auto en `disconnected` les devices sans heartbeat
  * Détectent les LocalAgent morts depuis > 7j

Toutes gèrent les erreurs silencieusement — pas de crash Celery.
"""
from __future__ import annotations

import logging
import socket
import time
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Seuils
HEARTBEAT_TIMEOUT_SECONDS = 120
AGENT_STALE_DAYS = 7
STATUS_CACHE_KEY = "device_realtime_status:{device_id}"   # cache dernier statut connu
STATUS_CACHE_TTL = 3600


# ═══════════════════════════════════════════════════════════════════
# 1) DeviceCommand timeouts
# ═══════════════════════════════════════════════════════════════════
@shared_task(name="devices.sweep_command_timeouts")
def sweep_command_timeouts():
    """Passe en status='timeout' les DeviceCommand qui ont dépassé timeout_at."""
    from .services.command_queue import DeviceCommandQueue
    try:
        n = DeviceCommandQueue.sweep_timeouts()
        if n:
            logger.info("Sweep commands : %d passages en timeout", n)
        return {"timeouted": n}
    except Exception as exc:
        logger.exception("sweep_command_timeouts KO : %s", exc)
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════
# 2) Reconcile device status
# ═══════════════════════════════════════════════════════════════════
@shared_task(name="devices.reconcile_status")
def reconcile_status():
    """Réconcilie les statuts device online/offline.

    Règles :
      1. Si heartbeat < 90s → considéré ONLINE
      2. Si heartbeat vieux OU absent → probe TCP best-effort
         - Si TCP OK → ONLINE (peut-être terminal muet mais joignable)
         - Sinon → OFFLINE
      3. Émet un event `device.connected` / `device.disconnected` UNIQUEMENT
         quand le statut change (déduplication via cache)
    """
    from .models import Device
    from .services.event_bus import EventBus

    now = timezone.now()
    cutoff = now - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)

    stats = {"checked": 0, "online": 0, "offline": 0,
              "transitions_online": 0, "transitions_offline": 0}

    # On limite au tenant actif (status="active") — pas la peine de sonder les archivés
    devices = (Device.objects.select_related("model")
                              .filter(status="active"))

    for d in devices:
        stats["checked"] += 1
        prev_status = cache.get(STATUS_CACHE_KEY.format(device_id=d.pk))

        # Étape 1 : heartbeat récent ?
        if d.last_heartbeat_at and d.last_heartbeat_at > cutoff:
            new_status = "online"
        else:
            # Étape 2 : probe TCP
            probe_ok = _probe_device(d)
            new_status = "online" if probe_ok else "offline"

        if new_status == "online":
            stats["online"] += 1
        else:
            stats["offline"] += 1

        # Étape 3 : transition ?
        if prev_status != new_status:
            cache.set(STATUS_CACHE_KEY.format(device_id=d.pk),
                       new_status, STATUS_CACHE_TTL)
            if new_status == "online":
                EventBus.emit_device_connected(d.pk, d.serial_number)
                stats["transitions_online"] += 1
            else:
                EventBus.emit_device_disconnected(d.pk, d.serial_number)
                stats["transitions_offline"] += 1

    if stats["transitions_online"] or stats["transitions_offline"]:
        logger.info(
            "Reconcile status : %d devices, ↑%d ↓%d",
            stats["checked"],
            stats["transitions_online"], stats["transitions_offline"],
        )

    # Refresh gauge Prometheus
    try:
        from core.metrics import devices_online
        devices_online.labels(device_type="all").set(stats["online"])
    except Exception:
        pass

    return stats


def _probe_device(device) -> bool:
    """TCP probe rapide selon le type d'équipement (comme EquipmentHealthMonitor)."""
    if not device.ip_address:
        return False
    type_ports = {
        "face_terminal":     [4370, 80],
        "portique":          [5084, 80],
        "camera":            [554, 80],
        "reader_uhf_fixed":  [5084, 80],
        "reader_uhf_mobile": [5084, 80],
        "reader_nfc_fixed":  [80, 443],
        "reader_nfc_mobile": [80, 443],
    }
    t = getattr(getattr(device, "model", None), "type", "") or ""
    ports = type_ports.get(t, [80, 4370, 5084, 554])
    for p in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.7)
                if s.connect_ex((device.ip_address, p)) == 0:
                    return True
        except Exception:
            continue
    return False


# ═══════════════════════════════════════════════════════════════════
# 3) Sweep stale LocalAgents
# ═══════════════════════════════════════════════════════════════════
@shared_task(name="devices.sweep_stale_agents")
def sweep_stale_agents():
    """Détecte les agents locaux morts.

    Un agent est considéré STALE si :
      - jamais vu (last_seen_at is null), et créé il y a > AGENT_STALE_DAYS
      - OU last_seen_at < now - AGENT_STALE_DAYS

    Action : marque `connected=False` et push une notification "agent_stale".
    Ne supprime PAS — l'admin peut décider de rotate ou révoquer.
    """
    from .models import LocalAgent

    cutoff = timezone.now() - timedelta(days=AGENT_STALE_DAYS)
    stale = []
    from django.db.models import Q
    for a in LocalAgent.objects.filter(
        Q(last_seen_at__lt=cutoff)
        | (Q(last_seen_at__isnull=True) & Q(created_at__lt=cutoff))
    ):
        # Reset flag connected si jamais resté à True
        if a.connected:
            a.connected = False
            a.channel_name = ""
            a.save(update_fields=["connected", "channel_name"])
        stale.append({
            "id": str(a.pk), "label": a.label, "tenant_id": a.tenant_id,
            "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
        })

    # Broadcast alerts pour chaque tenant
    if stale:
        from .services.event_bus import EventBus
        for s in stale:
            EventBus._broadcast("device.status", {
                "type": "agent.event",
                "event": "agent.stale",
                "agent_id": s["id"],
                "label": s["label"],
                "last_seen_at": s["last_seen_at"],
                "at": timezone.now().isoformat(),
            })
        logger.info("Stale agents détectés : %d", len(stale))

    return {"stale_count": len(stale), "stale": stale}


# ═══════════════════════════════════════════════════════════════════
# 4) Sync alertes système en DB (persistance + routing notifications)
# ═══════════════════════════════════════════════════════════════════
@shared_task(name="devices.sweep_system_alerts")
def sweep_system_alerts():
    """Détecte les conditions d'alerte système et matérialise en ``SystemAlert``.

    Idempotent : appelé toutes les 60s, met à jour ou crée selon (kind, target_id).
    Résout automatiquement les alertes dont la condition n'est plus vraie.
    """
    from datetime import timedelta

    from .models import (Device, DeviceCommand, LocalAgent,
                          RFIDEnrollmentSession)
    from .services.alert_service import AlertService

    now = timezone.now()

    # Per-tenant sweep — on scanne l'ensemble des tenants ayant au moins un device ou agent
    from core.models import Tenant
    tenants = Tenant.objects.filter(is_active=True)

    total_raised = 0
    total_resolved = 0

    for tenant in tenants:
        # 1) AGENT_OFFLINE
        agent_cutoff_warning = now - timedelta(minutes=5)
        agent_cutoff_critical = now - timedelta(hours=1)
        active_agent_targets = set()

        for a in LocalAgent.objects.filter(tenant=tenant):
            seen = a.last_seen_at
            if a.connected:
                continue
            if seen is None or seen < agent_cutoff_critical:
                sev = "critical"
            elif seen < agent_cutoff_warning:
                sev = "warning"
            else:
                continue
            AlertService.raise_alert(
                tenant=tenant, kind="agent_offline", severity=sev,
                title=f"Agent hors ligne : {a.label}",
                detail=(f"Dernier signe : {seen.strftime('%d/%m %H:%M')}"
                        if seen else "Jamais connecté"),
                target_url="/local-agents", target_id=str(a.pk),
            )
            active_agent_targets.add(str(a.pk))
            total_raised += 1

        # Résolution auto : les agents non listés sont "back online"
        from .models import SystemAlert
        for stale in SystemAlert.objects.filter(
            tenant=tenant, kind="agent_offline", resolved_at__isnull=True,
        ).exclude(target_id__in=active_agent_targets):
            stale.resolved_at = now
            stale.save(update_fields=["resolved_at"])
            total_resolved += 1

        # 2) DEVICE_OFFLINE
        dev_cutoff = now - timedelta(minutes=5)
        active_dev_targets = set()
        for d in (Device.objects.select_related("model")
                                 .filter(tenant=tenant, status="active",
                                          last_heartbeat_at__lt=dev_cutoff)
                                 .exclude(last_heartbeat_at__isnull=True)[:100]):
            age_min = int((now - d.last_heartbeat_at).total_seconds() // 60)
            sev = "critical" if age_min >= 60 else "warning"
            AlertService.raise_alert(
                tenant=tenant, kind="device_offline", severity=sev,
                title=f"Terminal hors ligne : {d.serial_number}",
                detail=f"{d.model.brand} {d.model.model} — heartbeat il y a {age_min} min",
                target_url=f"/devices/{d.pk}", target_id=str(d.pk),
            )
            active_dev_targets.add(str(d.pk))
            total_raised += 1

        for stale in SystemAlert.objects.filter(
            tenant=tenant, kind="device_offline", resolved_at__isnull=True,
        ).exclude(target_id__in=active_dev_targets):
            stale.resolved_at = now
            stale.save(update_fields=["resolved_at"])
            total_resolved += 1

        # 3) SESSION_STALLED
        sess_cutoff = now - timedelta(minutes=3)
        active_sess_targets = set()
        for s in RFIDEnrollmentSession.objects.filter(
            tenant=tenant, status="listening",
            started_at__lt=sess_cutoff, scans_count=0,
        )[:50]:
            AlertService.raise_alert(
                tenant=tenant, kind="session_stalled", severity="warning",
                title="Session d'enrôlement sans scan",
                detail=f"Session ouverte depuis {s.started_at.strftime('%H:%M')}",
                target_url="/badges", target_id=str(s.pk),
            )
            active_sess_targets.add(str(s.pk))
            total_raised += 1

        for stale in SystemAlert.objects.filter(
            tenant=tenant, kind="session_stalled", resolved_at__isnull=True,
        ).exclude(target_id__in=active_sess_targets):
            stale.resolved_at = now
            stale.save(update_fields=["resolved_at"])
            total_resolved += 1

        # 4) COMMAND_TIMEOUT (dernière heure)
        cmd_cutoff = now - timedelta(hours=1)
        for c in (DeviceCommand.objects.filter(
            tenant=tenant, status="timeout", completed_at__gte=cmd_cutoff,
        ).select_related("device")[:30]):
            AlertService.raise_alert(
                tenant=tenant, kind="command_timeout", severity="info",
                title=f"Commande sans réponse : {c.kind}",
                detail=(f"{c.device.serial_number} — timeout à "
                        f"{c.completed_at.strftime('%H:%M')}"),
                target_url=f"/devices/{c.device_id}", target_id=str(c.pk),
                route_notifications=False,
            )
            total_raised += 1

    if total_raised or total_resolved:
        logger.info("Alerts sweep : raised=%d resolved=%d",
                     total_raised, total_resolved)
    return {"raised": total_raised, "resolved": total_resolved}


# ═══════════════════════════════════════════════════════════════════
# 5) Refresh périodique des Digital Twins (Vague 7)
# ═══════════════════════════════════════════════════════════════════
@shared_task(name="devices.run_predictive_maintenance")
def run_predictive_maintenance():
    """Analyse tous les devices et génère les MaintenanceTicket automatiques.

    Idempotent : les tickets existants sont mis à jour, pas dupliqués.
    Les tickets résolus (condition levée) passent à 'resolved' automatiquement.
    """
    from .services.maintenance import PredictiveMaintenanceEngine
    return PredictiveMaintenanceEngine.analyze_all()


@shared_task(name="devices.refresh_device_twins")
def refresh_device_twins():
    """Rafraîchit tous les Digital Twins des devices actifs via leurs drivers.

    Batch limité et thread-poolé implicitement par les drivers (chacun a son
    propre timeout court). Idempotent — appel toutes les 2 minutes.
    """
    from .models import Device
    from .services.twin_service import TwinService

    devices = list(Device.objects.select_related("model")
                                  .filter(status="active")[:500])
    stats = TwinService.refresh_batch(devices, use_driver=True)
    logger.info("Twins refresh : ok=%d ko=%d (total=%d)",
                 stats["ok"], stats["ko"], len(devices))
    return stats


# ═══════════════════════════════════════════════════════════════════
# 6) OTA firmware push réel (Vague 10)
# ═══════════════════════════════════════════════════════════════════
@shared_task(name="devices.process_pending_ota_updates")
def process_pending_ota_updates():
    """Traite tous les OTAUpdate en statut ``scheduled``.

    Chaque OTA est délégué au driver du device concerné via ``update_firmware()``.
    Si le driver ne supporte pas → passage en `failed`. Sinon on marque
    `in_progress`, on attend la réponse driver, puis `succeeded` / `failed`.
    """
    from .drivers import DriverManager
    from .models import OTAUpdate

    stats = {"processed": 0, "succeeded": 0, "failed": 0, "unsupported": 0}

    pending = OTAUpdate.objects.filter(status="scheduled").select_related(
        "device", "device__model", "firmware",
    )[:20]
    for ota in pending:
        stats["processed"] += 1
        ota.status = "in_progress"
        ota.started_at = timezone.now()
        ota.save(update_fields=["status", "started_at"])

        device = ota.device
        driver = DriverManager.for_device(device)
        # URL du fichier firmware à télécharger par le device
        firmware_url = ""
        checksum = ""
        try:
            if ota.firmware and getattr(ota.firmware, "file", None):
                # URL absolue non résolvable ici — le device n'a pas de contexte
                # request. On stocke seulement le path relatif ; l'admin ou le
                # driver doit résoudre l'URL absolue si besoin.
                firmware_url = str(ota.firmware.file.url) if ota.firmware.file else ""
            checksum = getattr(ota.firmware, "checksum_sha256", "") or ""
        except Exception:
            pass

        try:
            with driver:
                result = driver.update_firmware(firmware_url=firmware_url,
                                                  checksum=checksum)
        except Exception as exc:
            ota.status = "failed"
            ota.finished_at = timezone.now()
            ota.error_message = f"Exception driver : {exc}"
            ota.save(update_fields=["status", "finished_at", "error_message"])
            stats["failed"] += 1
            continue

        if not result.ok:
            # Distinguer "non supporté" (info) de "vraie erreur"
            if "ne supporte pas" in (result.detail or ""):
                stats["unsupported"] += 1
                ota.status = "failed"
                ota.error_message = f"Driver {driver.vendor} ne supporte pas update_firmware()"
            else:
                stats["failed"] += 1
                ota.status = "failed"
                ota.error_message = result.detail or "erreur inconnue"
            ota.finished_at = timezone.now()
            ota.save(update_fields=["status", "finished_at", "error_message"])
            continue

        # Le driver a accepté — soit synchrone (succeeded direct), soit
        # asynchrone (le device confirme via une commande ADMS plus tard).
        ota.status = "succeeded"
        ota.finished_at = timezone.now()
        ota.save(update_fields=["status", "finished_at"])
        stats["succeeded"] += 1

        try:
            from .services.event_bus import EventBus
            EventBus.emit_device_status(device.pk, device.serial_number,
                                          "firmware_updated",
                                          payload={"ota_id": ota.pk,
                                                    "firmware_id": ota.firmware_id})
        except Exception:
            pass

    if stats["processed"]:
        logger.info("OTA sweep : %s", stats)
    return stats


@shared_task(name="devices.mqtt_health_ping")
def mqtt_health_ping():
    """Publie un heartbeat sur ``kshield/health/ping`` toutes les 5 min.

    Utilité :
      * Vérifier depuis un moniteur externe (MQTTX, mosquitto_sub) que le
        publisher Django fonctionne réellement en prod
      * Vérifier depuis le dashboard EMQX que les messages entrants
        arrivent — utile pour valider la config broker
      * Détecter si le publisher se déconnecte silencieusement (compteur
        Prometheus custom `kshield_mqtt_health_pings_total`)

    Payload : {"at": "ISO8601", "hostname": "...", "revision": "..."}
    """
    from django.utils import timezone
    import socket

    from devices.services.mqtt_publisher import publish_broadcast

    payload = {
        "at":       timezone.now().isoformat(),
        "source":   "django-celery-beat",
        "hostname": socket.gethostname(),
    }
    result = publish_broadcast("health.ping", payload=payload, qos=0)
    if result.get("ok"):
        logger.debug("MQTT health ping OK: %s", result.get("action_id"))
    else:
        logger.warning("MQTT health ping ÉCHEC: %s", result.get("error"))
    return result
