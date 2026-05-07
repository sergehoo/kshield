"""Middleware injectant l'IP & UA dans le contexte d'audit pour les signaux."""
import threading

_ctx = threading.local()


def get_audit_context():
    return {
        "ip": getattr(_ctx, "ip", None),
        "user_agent": getattr(_ctx, "user_agent", ""),
    }


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _ctx.ip = request.META.get("REMOTE_ADDR")
        _ctx.user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        return self.get_response(request)
