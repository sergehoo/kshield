"""KAYDAN SHIELD — routage WebSocket devices/enrôlement.

Monté dans kshield/asgi.py via :
    from devices.routing import websocket_urlpatterns as devices_ws
    ...
    URLRouter(access_ws + notif_ws + devices_ws)
"""
from django.urls import re_path

from .consumers import (AgentConsumer, DeviceStatusConsumer,
                         EnrollmentSessionConsumer, EventsLiveConsumer)

websocket_urlpatterns = [
    re_path(
        r"^ws/rfid/enrollment/(?P<session_id>[0-9a-f-]{36})/?$",
        EnrollmentSessionConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/devices/status/?$",
        DeviceStatusConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/agents/(?P<agent_id>\d+)/?$",
        AgentConsumer.as_asgi(),
    ),
    # Phase 2 — flux temps réel des événements techniques par tenant
    re_path(
        r"^ws/events/(?P<tenant_id>\d+)/?$",
        EventsLiveConsumer.as_asgi(),
    ),
]
