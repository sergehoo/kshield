"""LocalAgentService — orchestration agents locaux (Phase 6 refonte §5).

Responsabilités :
  - ingest_heartbeat : persiste heartbeat + trigger alertes auto
  - configure : crée nouvelle version de config
  - apply_config : marque version comme is_current
  - health_check : évalue les 7 règles d'alertes (§5.5)
  - transitions : start/stop/restart/update via publisher MQTT
  - device attach/detach : lien LocalAgent ↔ Device

Règles d'alertes automatiques (§5.5) :
  1. Heartbeat absent > threshold → agent_stale
  2. Queue file d'attente > threshold → agent_queue_full
  3. Erreurs > threshold sur dernière heure → agent_error_burst
  4. Devices attendus > connectés → devices_unreachable
  5. Version obsolète (agent < last_release) → agent_version_outdated
  6. Sync bloquée > 1h → agent_sync_blocked
  7. Storage disponible < 10% → agent_storage_low
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Config seuils (surchargeables via settings.KSHIELD_AGENT_THRESHOLDS)
# ═══════════════════════════════════════════════════════════════════
DEFAULT_THRESHOLDS = {
    "heartbeat_stale_seconds":   300,     # 5 min sans hb → alerte
    "queue_full":                1000,    # > 1000 events pending
    "errors_burst":              50,      # > 50 erreurs / heure
    "storage_low_percent":       10.0,    # < 10% dispo
    "sync_blocked_seconds":      3600,    # > 1h sans sync
    "cpu_high":                  90.0,
    "memory_high":               90.0,
}


# ═══════════════════════════════════════════════════════════════════
# Result
# ═══════════════════════════════════════════════════════════════════
@dataclass
class AgentResult:
    ok: bool
    agent: Any = None
    heartbeat: Any = None
    alerts_triggered: Optional[list] = None
    error: str = ""
    error_code: str = ""


# ═══════════════════════════════════════════════════════════════════
# LocalAgentService
# ═══════════════════════════════════════════════════════════════════
class LocalAgentService:
    """Service stateless — méthodes de classe."""

    # ─── Ingest heartbeat + alertes ──────────────────────────────
    @classmethod
    @transaction.atomic
    def ingest_heartbeat(
        cls, agent, payload: dict,
    ) -> AgentResult:
        """Persiste un heartbeat + trigger alertes automatiques.

        Payload attendu (envoyé par l'agent Go) :
          {
            "sent_at": "ISO8601",
            "state": "running",
            "version": "1.2.3",
            "uptime_seconds": 12345,
            "cpu_percent": 45.2, "memory_percent": 60.1,
            "memory_mb": 512, "storage_percent": 30.5,
            "storage_free_mb": 5000, "network_latency_ms": 15,
            "events_processed": 1234, "events_pending": 5,
            "devices_connected": 3, "devices_expected": 4,
            "errors_last_hour": 2, "sync_last_success_at": "ISO",
            "recent_errors": [...]
          }
        """
        from devices.models_agents import LocalAgentHeartbeat, AgentState

        payload = payload or {}
        sent_at = payload.get("sent_at")
        if sent_at:
            from django.utils.dateparse import parse_datetime
            sent_at = parse_datetime(sent_at) or timezone.now()
        else:
            sent_at = timezone.now()

        state = payload.get("state") or AgentState.RUNNING
        if state not in dict(AgentState.choices):
            state = AgentState.RUNNING

        # Truncate recent_errors à 20 items max
        recent_errors = payload.get("recent_errors") or []
        if isinstance(recent_errors, list):
            recent_errors = recent_errors[:20]
        else:
            recent_errors = []

        hb = LocalAgentHeartbeat.objects.create(
            agent=agent, tenant=agent.tenant,
            sent_at=sent_at,
            state=state,
            version=(payload.get("version") or "")[:32],
            uptime_seconds=int(payload.get("uptime_seconds") or 0),
            cpu_percent=float(payload.get("cpu_percent") or 0),
            memory_percent=float(payload.get("memory_percent") or 0),
            memory_mb=int(payload.get("memory_mb") or 0),
            storage_percent=float(payload.get("storage_percent") or 0),
            storage_free_mb=int(payload.get("storage_free_mb") or 0),
            network_latency_ms=int(payload.get("network_latency_ms") or 0),
            events_processed=int(payload.get("events_processed") or 0),
            events_pending=int(payload.get("events_pending") or 0),
            devices_connected=int(payload.get("devices_connected") or 0),
            devices_expected=int(payload.get("devices_expected") or 0),
            errors_last_hour=int(payload.get("errors_last_hour") or 0),
            sync_last_success_at=payload.get("sync_last_success_at"),
            recent_errors=recent_errors,
            metadata=payload.get("metadata") or {},
        )

        # Update LocalAgent.last_seen_at + status
        agent.last_seen_at = timezone.now()
        agent.connected = state == AgentState.RUNNING
        # Copie état pour lecture rapide
        if hasattr(agent, "version"):
            agent.version = (payload.get("version") or agent.version)[:32]
        agent.save(update_fields=[
            "last_seen_at", "connected", "version",
        ] if hasattr(agent, "version") else ["last_seen_at", "connected"])

        # Trigger alertes auto
        alerts = cls._evaluate_health(agent, hb)

        return AgentResult(ok=True, agent=agent, heartbeat=hb,
                            alerts_triggered=alerts)

    # ─── Évaluation santé + alertes ──────────────────────────────
    @classmethod
    def _evaluate_health(cls, agent, hb) -> list:
        """Applique les 7 règles §5.5 et déclenche EventService.record()
        pour chaque alerte détectée. Retourne list[str] des alertes créées.
        """
        from django.conf import settings
        thresholds = {**DEFAULT_THRESHOLDS,
                      **getattr(settings, "KSHIELD_AGENT_THRESHOLDS", {})}
        alerts_created = []

        # 2. Queue full
        if hb.events_pending > thresholds["queue_full"]:
            cls._emit_alert(agent, "LOCAL_QUEUE_PENDING",
                             message=f"File d'attente offline saturée : "
                                       f"{hb.events_pending} events pending",
                             severity="warning")
            alerts_created.append("queue_full")

        # 3. Errors burst
        if hb.errors_last_hour > thresholds["errors_burst"]:
            cls._emit_alert(agent, "DEVICE_ERROR",
                             message=f"Burst d'erreurs : "
                                       f"{hb.errors_last_hour}/h",
                             severity="warning")
            alerts_created.append("errors_burst")

        # 4. Devices unreachable
        if (hb.devices_expected > 0 and
                hb.devices_connected < hb.devices_expected):
            missing = hb.devices_expected - hb.devices_connected
            cls._emit_alert(agent, "DEVICE_UNREACHABLE",
                             message=f"{missing} équipement(s) inaccessible(s)",
                             severity="warning")
            alerts_created.append("devices_unreachable")

        # 5. Version obsolète
        if hb.version and hasattr(agent, "site"):
            latest = cls._get_latest_release_version(agent)
            if latest and cls._version_lt(hb.version, latest):
                cls._emit_alert(agent, "LOCAL_AGENT_UPDATED",
                                 message=f"Version obsolète : {hb.version} "
                                           f"(dispo : {latest})",
                                 severity="info")
                alerts_created.append("version_outdated")

        # 6. Sync bloquée
        if hb.sync_last_success_at:
            delta = (timezone.now() - hb.sync_last_success_at).total_seconds()
            if delta > thresholds["sync_blocked_seconds"]:
                cls._emit_alert(agent, "EDGE_SYNC_FAILED",
                                 message=f"Sync bloquée depuis "
                                           f"{int(delta / 60)} min",
                                 severity="warning")
                alerts_created.append("sync_blocked")

        # 7. Storage low
        if 0 < hb.storage_percent < thresholds["storage_low_percent"]:
            cls._emit_alert(agent, "DEVICE_ERROR",
                             message=f"Stockage local faible : "
                                       f"{hb.storage_percent:.1f}% dispo",
                             severity="warning")
            alerts_created.append("storage_low")

        return alerts_created

    @staticmethod
    def _emit_alert(agent, event_code: str, message: str, severity: str):
        """Crée un DeviceEvent via EventService (auto SystemAlert si besoin)."""
        try:
            from devices.services.events import EventService
            EventService.record(
                code=event_code,
                tenant=agent.tenant,
                agent=agent,
                gateway=agent,   # LocalAgent = gateway ici
                site=agent.site if hasattr(agent, "site") else None,
                message=message[:2000],
                severity=severity,
            )
        except Exception as e:
            logger.warning("Impossible d'émettre alerte %s : %s", event_code, e)

    @staticmethod
    def _get_latest_release_version(agent) -> Optional[str]:
        """Retourne la dernière version publiée pour la plateforme de l'agent."""
        try:
            from devices.models import EdgeGatewayPackage
            latest = EdgeGatewayPackage.objects.filter(
                is_latest=True,
            ).order_by("-published_at").first()
            return latest.version if latest else None
        except Exception:
            return None

    @staticmethod
    def _version_lt(a: str, b: str) -> bool:
        """Compare 2 versions semver (naif — X.Y.Z uniquement)."""
        try:
            aa = [int(x) for x in a.split(".")[:3]]
            bb = [int(x) for x in b.split(".")[:3]]
            return aa < bb
        except (ValueError, AttributeError):
            return False

    # ─── Détection agents stale (task Celery beat) ───────────────
    @classmethod
    def sweep_stale_agents(cls, thresholds: Optional[dict] = None) -> dict:
        """Marque les agents comme stale/unreachable si pas de heartbeat
        récent. À appeler périodiquement.
        """
        from devices.models import LocalAgent
        from devices.models_agents import AgentState

        t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        threshold_at = timezone.now() - timedelta(
            seconds=t["heartbeat_stale_seconds"],
        )

        stale_qs = LocalAgent.objects.filter(
            last_seen_at__lt=threshold_at, connected=True,
        )
        stale_count = 0
        for agent in stale_qs:
            agent.connected = False
            agent.save(update_fields=["connected"])
            cls._emit_alert(agent, "GATEWAY_OFFLINE",
                             message=f"Agent inactif depuis "
                                       f"{t['heartbeat_stale_seconds']}s",
                             severity="critical")
            stale_count += 1

        return {"stale_agents": stale_count}

    # ─── Configuration versionnée ────────────────────────────────
    @classmethod
    @transaction.atomic
    def create_configuration(
        cls, agent, payload: dict, notes: str = "",
        make_current: bool = False,
    ) -> AgentResult:
        """Crée une nouvelle version de config pour un agent."""
        from devices.models_agents import LocalAgentConfiguration

        # Version = max(current) + 1
        last = LocalAgentConfiguration.objects.filter(agent=agent)\
                    .order_by("-version").first()
        version = (last.version + 1) if last else 1

        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        checksum = hashlib.sha256(payload_str.encode()).hexdigest()

        # Vérifie dédup (payload identique à la current)
        current = LocalAgentConfiguration.objects.filter(
            agent=agent, is_current=True,
        ).first()
        if current and current.checksum == checksum:
            return AgentResult(ok=True, agent=agent,
                                error_code="unchanged",
                                error="Config identique à la version courante")

        config = LocalAgentConfiguration.objects.create(
            agent=agent, version=version, payload=payload,
            checksum=checksum, notes=notes[:2000],
            is_draft=not make_current, is_current=False,
        )
        if make_current:
            cls._make_config_current(agent, config)
        return AgentResult(ok=True, agent=agent, heartbeat=None)

    @classmethod
    @transaction.atomic
    def apply_configuration(cls, agent, config) -> AgentResult:
        """Marque une config comme courante (l'agent doit pull la version)."""
        from devices.models_agents import LocalAgentConfiguration
        # Vérifie appartenance
        if config.agent_id != agent.pk:
            return AgentResult(ok=False, error_code="wrong_agent",
                                error="Config n'appartient pas à cet agent")
        cls._make_config_current(agent, config)
        # Envoie commande MQTT à l'agent pour pull la nouvelle version
        try:
            from devices.services.mqtt_publisher import publish_command
            publish_command(
                gateway_id=str(agent.pk),
                action_type="config_updated",
                payload={"version": config.version,
                         "checksum": config.checksum},
            )
        except Exception as e:
            logger.debug("MQTT publish config_updated failed: %s", e)
        return AgentResult(ok=True, agent=agent)

    @staticmethod
    def _make_config_current(agent, config):
        """Atomically : reset all is_current=False puis set config.is_current=True."""
        from devices.models_agents import LocalAgentConfiguration
        LocalAgentConfiguration.objects.filter(agent=agent).update(is_current=False)
        config.is_current = True
        config.is_draft = False
        config.applied_at = timezone.now()
        config.save(update_fields=["is_current", "is_draft", "applied_at"])

    # ─── Actions runtime (via MQTT publisher) ────────────────────
    @classmethod
    def send_command(
        cls, agent, command: str, payload: Optional[dict] = None,
    ) -> AgentResult:
        """Envoie une commande MQTT à un agent.

        Commandes standard : start, stop, restart, update, test, reload_config,
        collect_logs, purge_cache, sync_now, uninstall.
        """
        try:
            from devices.services.mqtt_publisher import publish_command
            result = publish_command(
                gateway_id=str(agent.pk),
                action_type=command,
                payload=payload or {},
            )
            if result.get("ok"):
                return AgentResult(ok=True, agent=agent)
            return AgentResult(ok=False, agent=agent,
                                error_code="mqtt_publish_failed",
                                error=result.get("error", ""))
        except Exception as e:
            return AgentResult(ok=False, agent=agent,
                                error_code="exception",
                                error=str(e))

    # ─── Logs ingestion ──────────────────────────────────────────
    @classmethod
    def ingest_logs(cls, agent, entries: list) -> int:
        """Bulk-insert des logs d'un agent. Retourne count inséré."""
        from devices.models_agents import LocalAgentLog, LogLevel

        to_create = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ts = entry.get("ts")
            if ts:
                from django.utils.dateparse import parse_datetime
                ts = parse_datetime(ts) or timezone.now()
            else:
                ts = timezone.now()
            level = entry.get("level", "info").lower()
            if level not in dict(LogLevel.choices):
                level = "info"
            to_create.append(LocalAgentLog(
                agent=agent, ts=ts, level=level,
                message=(entry.get("message") or "")[:8000],
                context=entry.get("context") or {},
                source=(entry.get("source") or "")[:64],
            ))
        if to_create:
            LocalAgentLog.objects.bulk_create(
                to_create, ignore_conflicts=True,
            )
        return len(to_create)

    # ─── Requêtes lecture ────────────────────────────────────────
    @classmethod
    def get_latest_heartbeat(cls, agent):
        from devices.models_agents import LocalAgentHeartbeat
        return LocalAgentHeartbeat.objects.filter(agent=agent)\
                    .order_by("-received_at").first()

    @classmethod
    def get_heartbeat_history(cls, agent, limit: int = 100):
        from devices.models_agents import LocalAgentHeartbeat
        return list(LocalAgentHeartbeat.objects.filter(agent=agent)\
                        .order_by("-received_at")[:limit])

    @classmethod
    def get_recent_logs(cls, agent, level: str = "", limit: int = 200):
        from devices.models_agents import LocalAgentLog
        qs = LocalAgentLog.objects.filter(agent=agent)
        if level:
            qs = qs.filter(level=level)
        return list(qs.order_by("-ts")[:limit])
