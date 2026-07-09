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


class ApiAuditMiddleware:
    """Middleware qui audit toutes les mutations API (POST/PUT/PATCH/DELETE).

    Logue automatiquement :
        - user, tenant, IP, UA (via AuditContext)
        - méthode HTTP + path
        - statut de la réponse
        - hash chaîné pour immutabilité

    Filtre :
        - Ignore GET, HEAD, OPTIONS (lecture)
        - Ignore /metrics, /healthz, /readyz
        - Ignore les chemins statiques (/static, /media)
    """

    SKIP_METHODS = {"GET", "HEAD", "OPTIONS"}
    SKIP_PATHS = ("/metrics", "/healthz", "/readyz", "/static/", "/media/",
                    "/api/schema/", "/api/docs/", "/api/redoc/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Ne logue que les mutations API
        if request.method in self.SKIP_METHODS:
            return response
        path = request.path or ""
        if any(path.startswith(p) for p in self.SKIP_PATHS):
            return response
        if not path.startswith("/api/"):
            return response

        try:
            self._log(request, response)
        except Exception:
            # Ne jamais casser la request principale sur une erreur d'audit
            import logging
            logging.getLogger(__name__).exception("ApiAuditMiddleware KO")

        return response

    def _log(self, request, response):
        from .models import AuditLog

        user = getattr(request, "user", None)
        if not (user and getattr(user, "is_authenticated", False)):
            user = None
        tenant = getattr(user, "tenant", None) if user else None

        # Deviner action à partir de la méthode HTTP
        action_map = {"POST": "create", "PUT": "update", "PATCH": "update",
                        "DELETE": "delete"}
        action = action_map.get(request.method, "api_access")

        # Extraire ID cible depuis l'URL (dernier segment numérique/uuid)
        import re
        target_id = ""
        segments = [s for s in path_split(request.path) if s]
        for seg in reversed(segments):
            if re.match(r"^([0-9]+|[0-9a-f-]{20,})$", seg):
                target_id = seg
                break

        # Extrait le nom logique du modèle depuis /api/v1/<app>/<model>/…
        target_model = ""
        try:
            parts = [p for p in request.path.split("/") if p]
            if len(parts) >= 3 and parts[0] == "api":
                target_model = f"{parts[2]}.{parts[3]}" if len(parts) > 3 else parts[2]
        except Exception:
            pass

        AuditLog.objects.create(
            tenant=tenant, user=user, action=action,
            target_model=target_model[:120], target_id=target_id[:80],
            before={"method": request.method, "path": request.path},
            after={"status_code": response.status_code},
            ip=_ctx_ip(), user_agent=_ctx_ua(),
        )


def path_split(p):
    return [s for s in (p or "").split("/") if s]


def _ctx_ip():
    return getattr(_ctx, "ip", None)


def _ctx_ua():
    return getattr(_ctx, "user_agent", "")[:500]
