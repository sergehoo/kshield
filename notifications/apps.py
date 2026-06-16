from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        # Charge les signaux qui déclenchent les notifications automatiques
        # sur AccessEvent (refus carte, retard) et FraudAlert.
        try:
            from . import signals  # noqa: F401
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "notifications.signals non chargé — notifs auto désactivées",
            )
