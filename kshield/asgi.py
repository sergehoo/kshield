"""ASGI config for KAYDAN SHIELD — Channels routing."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kshield.settings.dev")
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402  (used indirectly via JWTAuthMiddlewareStack)  # noqa
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from kshield.ws_auth import JWTAuthMiddlewareStack  # noqa: E402

try:
    from access_control.routing import websocket_urlpatterns as access_ws
except Exception:  # pragma: no cover
    access_ws = []
try:
    from notifications.routing import websocket_urlpatterns as notif_ws
except Exception:  # pragma: no cover
    notif_ws = []
try:
    from devices.routing import websocket_urlpatterns as devices_ws
except Exception:  # pragma: no cover
    devices_ws = []

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # JWT en query string (?token=<JWT>) + fallback session Django.
        "websocket": JWTAuthMiddlewareStack(
            URLRouter(access_ws + notif_ws + devices_ws)
        ),
    }
)
