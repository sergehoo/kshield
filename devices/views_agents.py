"""KAYDAN SHIELD — API Agents locaux (Phase 6 refonte §5).

Endpoints agent (HMAC) :

    POST /api/v1/devices/agents/heartbeat/       (métriques + état)
    POST /api/v1/devices/agents/logs/            (bulk push logs)
    GET  /api/v1/devices/agents/config/          (pull config courante)

Endpoints admin (JWT) :

    GET  /api/v1/devices/agents/                 (list + filtres)
    GET  /api/v1/devices/agents/<id>/            (détail complet + latest hb)
    GET  /api/v1/devices/agents/<id>/heartbeats/ (historique)
    GET  /api/v1/devices/agents/<id>/logs/       (buffer live)
    GET  /api/v1/devices/agents/<id>/configs/    (versions config)
    POST /api/v1/devices/agents/<id>/configs/    (créer nouvelle version)
    POST /api/v1/devices/agents/<id>/configs/<v>/apply/  (apply version)
    POST /api/v1/devices/agents/<id>/commands/<cmd>/     (start/stop/restart/...)
    GET  /api/v1/devices/agents/types/           (catalogue LocalAgentType)
"""
from __future__ import annotations

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_hmac import AgentHmacAuthentication
from .models import LocalAgent
from .models_agents import (
    LocalAgentConfiguration, LocalAgentHeartbeat, LocalAgentLog,
    LocalAgentType,
)
from .services.agents import LocalAgentService
from .utils import resolve_tenant as _resolve_tenant


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════
def _hb_dict(hb) -> dict:
    if hb is None:
        return None
    return {
        "id":              str(hb.pk),
        "sent_at":         hb.sent_at.isoformat(),
        "received_at":     hb.received_at.isoformat(),
        "state":           hb.state,
        "version":         hb.version,
        "uptime_seconds":  hb.uptime_seconds,
        "cpu_percent":     hb.cpu_percent,
        "memory_percent":  hb.memory_percent,
        "memory_mb":       hb.memory_mb,
        "storage_percent": hb.storage_percent,
        "storage_free_mb": hb.storage_free_mb,
        "network_latency_ms": hb.network_latency_ms,
        "events_processed":  hb.events_processed,
        "events_pending":    hb.events_pending,
        "devices_connected": hb.devices_connected,
        "devices_expected":  hb.devices_expected,
        "errors_last_hour":  hb.errors_last_hour,
        "sync_last_success_at":
            hb.sync_last_success_at.isoformat() if hb.sync_last_success_at else None,
        "recent_errors":   hb.recent_errors,
    }


def _agent_dict(agent, latest_hb=None) -> dict:
    d = {
        "id":         str(agent.pk),
        "label":      agent.label,
        "site_id":    agent.site_id,
        "tenant_id":  agent.tenant_id,
        "connected":  agent.connected,
        "last_seen_at": agent.last_seen_at.isoformat() if agent.last_seen_at else None,
    }
    if hasattr(agent, "version"):
        d["version"] = agent.version
    if latest_hb:
        d["latest_heartbeat"] = _hb_dict(latest_hb)
    return d


def _config_dict(c) -> dict:
    return {
        "id":         str(c.pk),
        "version":    c.version,
        "checksum":   c.checksum,
        "is_current": c.is_current,
        "is_draft":   c.is_draft,
        "applied_at": c.applied_at.isoformat() if c.applied_at else None,
        "created_at": c.created_at.isoformat(),
        "notes":      c.notes,
        # payload seulement dans le détail — on l'omet ici pour la liste
    }


# ═══════════════════════════════════════════════════════════════════
# Endpoints AGENT (HMAC)
# ═══════════════════════════════════════════════════════════════════
class AgentHeartbeatView(APIView):
    """POST /agents/heartbeat/  — push métriques runtime."""
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        agent = getattr(request, "agent", None)
        if agent is None or agent.revoked_at:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)

        result = LocalAgentService.ingest_heartbeat(agent, request.data or {})
        return Response({
            "ok":                result.ok,
            "heartbeat_id":      str(result.heartbeat.pk) if result.heartbeat else None,
            "alerts_triggered":  result.alerts_triggered or [],
        })


class AgentLogsIngestView(APIView):
    """POST /agents/logs/  — bulk push logs.

    Body : {"entries": [{"ts": "ISO", "level": "info", "message": "...", "source": "..."}, ...]}
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)
        entries = (request.data or {}).get("entries") or []
        if not isinstance(entries, list):
            return Response({"error": "entries_must_be_list"},
                              status=http_status.HTTP_400_BAD_REQUEST)
        count = LocalAgentService.ingest_logs(agent, entries[:500])
        return Response({"ok": True, "ingested": count})


class AgentConfigPullView(APIView):
    """GET /agents/config/  — pull config courante."""
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def get(self, request):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)
        config = LocalAgentConfiguration.objects.filter(
            agent=agent, is_current=True,
        ).first()
        if not config:
            return Response({"config": None, "version": 0})
        return Response({
            "version":  config.version,
            "checksum": config.checksum,
            "payload":  config.payload,
            "applied_at": config.applied_at.isoformat() if config.applied_at else None,
        })


# ═══════════════════════════════════════════════════════════════════
# Endpoints ADMIN (JWT)
# ═══════════════════════════════════════════════════════════════════
class AgentListView(APIView):
    """GET /agents/  — liste agents avec dernier heartbeat."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "results": []})

        qs = LocalAgent.objects.filter(tenant=tenant)
        # Filtres
        connected = request.query_params.get("connected")
        if connected == "true":
            qs = qs.filter(connected=True)
        elif connected == "false":
            qs = qs.filter(connected=False)

        site = request.query_params.get("site")
        if site:
            qs = qs.filter(site_id=site)

        limit = min(int(request.query_params.get("limit", 100)), 500)
        total = qs.count()
        agents = qs.select_related("site")[:limit]

        results = []
        for a in agents:
            latest = LocalAgentService.get_latest_heartbeat(a)
            results.append(_agent_dict(a, latest_hb=latest))

        return Response({"count": total, "results": results})


class AgentDetailView(APIView):
    """GET /agents/<id>/  — détail complet."""
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            agent = LocalAgent.objects.get(pk=agent_id, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        latest_hb = LocalAgentService.get_latest_heartbeat(agent)
        return Response(_agent_dict(agent, latest_hb=latest_hb))


class AgentHeartbeatsListView(APIView):
    """GET /agents/<id>/heartbeats/  — historique."""
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "results": []})
        try:
            agent = LocalAgent.objects.get(pk=agent_id, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        limit = min(int(request.query_params.get("limit", 100)), 1000)
        hbs = LocalAgentService.get_heartbeat_history(agent, limit=limit)
        return Response({
            "count":   len(hbs),
            "results": [_hb_dict(h) for h in hbs],
        })


class AgentLogsListView(APIView):
    """GET /agents/<id>/logs/  — buffer logs live."""
    permission_classes = [IsAuthenticated]

    def get(self, request, agent_id):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "results": []})
        try:
            agent = LocalAgent.objects.get(pk=agent_id, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        level = request.query_params.get("level", "")
        limit = min(int(request.query_params.get("limit", 200)), 1000)
        logs = LocalAgentService.get_recent_logs(agent, level=level, limit=limit)
        return Response({
            "count":   len(logs),
            "results": [{
                "id":       str(l.pk),
                "ts":       l.ts.isoformat(),
                "level":    l.level,
                "message":  l.message,
                "source":   l.source,
                "context":  l.context,
            } for l in logs],
        })


class AgentConfigsView(APIView):
    """GET /agents/<id>/configs/  — versions config.
       POST /agents/<id>/configs/  — nouvelle version.
    """
    permission_classes = [IsAuthenticated]

    def _get_agent(self, request, agent_id):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return None, Response({"error": "no_tenant"},
                                    status=http_status.HTTP_403_FORBIDDEN)
        try:
            return LocalAgent.objects.get(pk=agent_id, tenant=tenant), None
        except LocalAgent.DoesNotExist:
            return None, Response({"error": "not_found"},
                                    status=http_status.HTTP_404_NOT_FOUND)

    def get(self, request, agent_id):
        agent, err = self._get_agent(request, agent_id)
        if err is not None:
            return err
        configs = LocalAgentConfiguration.objects.filter(agent=agent)\
                        .order_by("-version")
        return Response({
            "count":   configs.count(),
            "results": [_config_dict(c) for c in configs],
        })

    def post(self, request, agent_id):
        agent, err = self._get_agent(request, agent_id)
        if err is not None:
            return err
        data = request.data or {}
        payload = data.get("payload") or {}
        make_current = bool(data.get("make_current", False))
        result = LocalAgentService.create_configuration(
            agent, payload,
            notes=data.get("notes", ""),
            make_current=make_current,
        )
        if not result.ok:
            return Response({"error": result.error, "code": result.error_code},
                              status=http_status.HTTP_400_BAD_REQUEST)
        # Retourne la version créée
        latest = LocalAgentConfiguration.objects.filter(agent=agent)\
                        .order_by("-version").first()
        return Response({"ok": True, "config": _config_dict(latest)},
                          status=http_status.HTTP_201_CREATED)


class AgentConfigApplyView(APIView):
    """POST /agents/<id>/configs/<version>/apply/  — apply version."""
    permission_classes = [IsAuthenticated]

    def post(self, request, agent_id, version):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            agent = LocalAgent.objects.get(pk=agent_id, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "agent_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)
        try:
            config = LocalAgentConfiguration.objects.get(
                agent=agent, version=version,
            )
        except LocalAgentConfiguration.DoesNotExist:
            return Response({"error": "config_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        result = LocalAgentService.apply_configuration(agent, config)
        if not result.ok:
            return Response({"error": result.error, "code": result.error_code},
                              status=http_status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "config": _config_dict(config)})


class AgentCommandView(APIView):
    """POST /agents/<id>/commands/<cmd>/  — envoie commande MQTT.

    Commandes supportées : start, stop, restart, update, test, reload_config,
    collect_logs, purge_cache, sync_now, uninstall.
    """
    permission_classes = [IsAuthenticated]

    ALLOWED_COMMANDS = {
        "start", "stop", "restart", "update", "test",
        "reload_config", "collect_logs", "purge_cache",
        "sync_now", "uninstall",
    }

    def post(self, request, agent_id, cmd):
        if cmd not in self.ALLOWED_COMMANDS:
            return Response(
                {"error": "invalid_command",
                 "allowed": sorted(self.ALLOWED_COMMANDS)},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            agent = LocalAgent.objects.get(pk=agent_id, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        result = LocalAgentService.send_command(
            agent, cmd, payload=request.data or {},
        )
        if not result.ok:
            return Response({"error": result.error, "code": result.error_code},
                              status=http_status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "command": cmd})


class AgentTypesListView(APIView):
    """GET /agents/types/  — catalogue types disponibles."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        types = LocalAgentType.objects.filter(is_active=True).order_by("code")
        return Response({
            "count": types.count(),
            "results": [{
                "code":         t.code,
                "label":        t.label,
                "description":  t.description,
                "module_name":  t.module_name,
                "capabilities": t.capabilities,
                "icon":         t.icon,
                "is_system":    t.is_system,
            } for t in types],
        })
