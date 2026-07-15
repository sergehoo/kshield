"""KAYDAN SHIELD — Consumers WebSocket pour l'enrôlement RFID et le statut device.

Auth : JWT passé en query string ``?token=<jwt>``.
Trois canaux :

  1. /ws/rfid/enrollment/<session_id>/    → événements d'une session (front modal)
  2. /ws/devices/status/                   → événements globaux devices/agents
  3. /ws/agents/<agent_id>/                → canal push commandes vers l'Agent local
"""
from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Utilitaires JWT (auth par query string)
# ═══════════════════════════════════════════════════════════════════
async def _authenticate_from_query(scope):
    """Renvoie le user Django si un JWT valide est fourni via ?token=…, sinon None."""
    from channels.db import database_sync_to_async
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

    query = scope.get("query_string", b"").decode()
    params = parse_qs(query)
    token = (params.get("token") or [None])[0]
    if not token:
        return None

    @database_sync_to_async
    def _validate():
        try:
            jwt_auth = JWTAuthentication()
            validated = jwt_auth.get_validated_token(token)
            return jwt_auth.get_user(validated)
        except (InvalidToken, TokenError, Exception):
            return None

    return await _validate()


# ═══════════════════════════════════════════════════════════════════
# 1) Session d'enrôlement RFID
# ═══════════════════════════════════════════════════════════════════
class EnrollmentSessionConsumer(AsyncJsonWebsocketConsumer):
    """Client WS d'une session d'enrôlement.

    URL : /ws/rfid/enrollment/<session_id>/?token=<jwt>
    Group name : enrollment.<session_id>
    """

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.group_name = f"enrollment.{self.session_id}"

        user = await _authenticate_from_query(self.scope)
        if user is None or user.is_anonymous:
            logger.info("EnrollmentWS refusé : auth manquante ou invalide")
            await self.close(code=4001)
            return

        # RBAC minimal — la session doit appartenir au tenant du user
        from channels.db import database_sync_to_async
        from .models import RFIDEnrollmentSession

        @database_sync_to_async
        def _fetch():
            try:
                s = RFIDEnrollmentSession.objects.get(pk=self.session_id)
                return s if s.tenant_id == getattr(user, "tenant_id", None) else None
            except RFIDEnrollmentSession.DoesNotExist:
                return None

        session = await _fetch()
        if session is None:
            logger.info("EnrollmentWS refusé : session %s hors scope", self.session_id)
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "hello",
            "session_id": self.session_id,
            "status": session.status,
        })

    async def disconnect(self, code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Messages entrants du front — ping/pong essentiellement.

        Le front n'a pas à envoyer de scans par WS ; l'ingestion passe par REST.
        """
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    # Handler pour les events broadcastés par EventBus
    async def session_event(self, event):
        """Reçoit les payloads envoyés par ``EventBus._broadcast``.

        Le nom du handler doit matcher ``type`` du payload avec les ``.`` remplacés par ``_``.
        Ex. ``{"type": "session.event", ...}`` → handler ``session_event``.
        """
        # Retire les clefs internes Channels avant envoi au client
        payload = {k: v for k, v in event.items() if k != "type"}
        await self.send_json(payload)


# ═══════════════════════════════════════════════════════════════════
# 2) Statut global devices/agents
# ═══════════════════════════════════════════════════════════════════
class DeviceStatusConsumer(AsyncJsonWebsocketConsumer):
    """Client WS de la page statut globale.

    URL : /ws/devices/status/?token=<jwt>
    Group name : device.status
    """

    async def connect(self):
        user = await _authenticate_from_query(self.scope)
        if user is None or user.is_anonymous:
            await self.close(code=4001)
            return
        self.user = user
        await self.channel_layer.group_add("device.status", self.channel_name)
        await self.accept()
        await self.send_json({"type": "hello", "channel": "device.status"})

    async def disconnect(self, code):
        await self.channel_layer.group_discard("device.status", self.channel_name)

    async def device_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        await self.send_json(payload)

    async def agent_event(self, event):
        payload = {k: v for k, v in event.items() if k != "type"}
        await self.send_json(payload)


# ═══════════════════════════════════════════════════════════════════
# 3) Agent local — canal push commandes
# ═══════════════════════════════════════════════════════════════════
class AgentConsumer(AsyncJsonWebsocketConsumer):
    """Canal WS bi-directionnel vers un Agent local.

    URL : /ws/agents/<agent_id>/?token=<agent_api_token>
    Group name : agent.<agent_id>

    Le token ici n'est pas un JWT user mais le ``LocalAgent.api_token``.
    """

    async def connect(self):
        self.agent_id = self.scope["url_route"]["kwargs"]["agent_id"]

        query = self.scope.get("query_string", b"").decode()
        params = parse_qs(query)
        token = (params.get("token") or [None])[0]

        from channels.db import database_sync_to_async
        from django.utils import timezone

        from .models import LocalAgent

        @database_sync_to_async
        def _authenticate():
            try:
                agent = LocalAgent.objects.get(pk=self.agent_id, api_token=token)
                agent.connected = True
                agent.channel_name = self.channel_name
                agent.last_seen_at = timezone.now()
                agent.save(update_fields=["connected", "channel_name", "last_seen_at"])
                return agent
            except LocalAgent.DoesNotExist:
                return None

        agent = await _authenticate()
        if agent is None:
            await self.close(code=4001)
            return
        self.agent = agent

        self.group_name = f"agent.{self.agent_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Emet event global
        from .services.event_bus import EventBus
        EventBus.emit_agent_connected(self.agent_id, agent.label)

        try:
            from core.metrics import local_agents_connected
            local_agents_connected.inc()
        except Exception:
            pass

        await self.send_json({
            "type": "hello",
            "agent_id": str(self.agent_id),
            "welcome": f"Hello {agent.label}",
        })

    async def disconnect(self, code):
        if not getattr(self, "agent", None):
            return
        from channels.db import database_sync_to_async

        from .models import LocalAgent
        from .services.event_bus import EventBus

        @database_sync_to_async
        def _mark_offline():
            try:
                a = LocalAgent.objects.get(pk=self.agent_id)
                a.connected = False
                a.channel_name = ""
                a.save(update_fields=["connected", "channel_name"])
            except LocalAgent.DoesNotExist:
                pass

        await _mark_offline()
        EventBus.emit_agent_disconnected(self.agent_id, self.agent.label)
        try:
            from core.metrics import local_agents_connected
            local_agents_connected.dec()
        except Exception:
            pass
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Événements poussés par l'Agent local (scan RFID, ack commande, etc.)."""
        from channels.db import database_sync_to_async

        from .services.command_queue import DeviceCommandQueue
        from .services.enrollment import EnrollmentError, RFIDEnrollmentService

        event = content.get("event")
        if event == "rfid.card.detected":
            uid = content.get("uid")
            device_id = content.get("device_id")

            @database_sync_to_async
            def _process():
                from .models import Device
                device = None
                if device_id:
                    try:
                        device = Device.objects.get(pk=device_id)
                    except Device.DoesNotExist:
                        pass
                try:
                    return RFIDEnrollmentService.ingest_scan(
                        tenant=self.agent.tenant, uid=uid, device=device,
                        rssi=content.get("rssi"),
                        extra=content.get("extra") or {},
                    )
                except EnrollmentError as exc:
                    return {"error": exc.message, "code": exc.code}

            result = await _process()
            await self.send_json({"type": "ingest.ack", "result": result})

        elif event == "device.command.ack":
            await database_sync_to_async(DeviceCommandQueue.acknowledge)(
                content.get("command_id"),
            )
        elif event == "device.command.completed":
            await database_sync_to_async(DeviceCommandQueue.complete)(
                content.get("command_id"),
                response_raw=content.get("response_raw") or {},
                response_normalized=content.get("response_normalized") or {},
            )
        elif event == "device.command.failed":
            await database_sync_to_async(DeviceCommandQueue.fail)(
                content.get("command_id"),
                content.get("error") or "unknown",
            )
        elif event == "heartbeat":
            @database_sync_to_async
            def _update():
                from django.utils import timezone
                self.agent.last_seen_at = timezone.now()
                self.agent.save(update_fields=["last_seen_at"])
            await _update()
            await self.send_json({"type": "pong"})

    async def agent_message(self, event):
        """Reçoit les messages push serveur → agent (ex. nouvelles commandes)."""
        payload = {k: v for k, v in event.items() if k != "type"}
        await self.send_json(payload)


# ═══════════════════════════════════════════════════════════════════
# 4) Events Live — Phase 2 refonte cahier des charges §1.3
# ═══════════════════════════════════════════════════════════════════
class EventsLiveConsumer(AsyncJsonWebsocketConsumer):
    """Canal WS pour la vue Events Live (supervision temps réel).

    URL : /ws/events/<tenant_id>/?token=<jwt>
    Group name : events.<tenant_id>

    Le service ``devices.services.events.EventService`` broadcast sur ce
    group à chaque DeviceEvent créé. Le frontend reçoit un stream continu
    de payloads compacts (voir ``EventService.serialize_for_ws``).

    Filtre côté serveur : uniquement les events du tenant du user connecté
    (isolation multi-tenants stricte).

    Messages entrants supportés :
      {"type": "ping"} → renvoie {"type": "pong"} (keepalive)
      {"type": "subscribe", "filters": {...}} → filtre côté client (v2)
    """

    async def connect(self):
        user = await _authenticate_from_query(self.scope)
        if user is None or user.is_anonymous:
            await self.close(code=4001)
            return

        # Extrait tenant_id du path + vérifie que le user y a accès
        tenant_id = self.scope["url_route"]["kwargs"].get("tenant_id")
        if not tenant_id:
            await self.close(code=4400)
            return

        # Scope tenant : le user ne peut souscrire qu'au flux de SON tenant
        user_tenant_id = getattr(user, "tenant_id", None)
        if not user.is_superuser and str(user_tenant_id) != str(tenant_id):
            await self.close(code=4003)
            return

        self.user = user
        self.tenant_id = tenant_id
        self.group_name = f"events.{tenant_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            "type": "hello",
            "channel": self.group_name,
            "server_time": timezone.now().isoformat(),
        })

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Traite les messages entrants (ping keepalive uniquement pour l'instant)."""
        msg_type = content.get("type", "")
        if msg_type == "ping":
            await self.send_json({
                "type": "pong",
                "server_time": timezone.now().isoformat(),
            })

    async def event_new(self, event):
        """Handler appelé quand EventService broadcast un DeviceEvent.

        Le service push :
            group_send(group, {"type": "event.new", "payload": {...}})
        Ce qui traduit en Python : event["type"] = "event.new" → resolve
        la méthode ``event_new`` (underscore convention Channels).
        """
        payload = event.get("payload") or {}
        await self.send_json({"type": "event", "data": payload})
