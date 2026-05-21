from django.apps import AppConfig


class SSOConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sso"
    verbose_name = "KAYDAN SSO (Keycloak)"

    def ready(self):
        # Branche les signals (audit login + invalidation cache)
        try:
            from . import signals  # noqa: F401
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "sso.signals indisponible", exc_info=True)
