from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    NotificationPreferenceViewSet, NotificationTemplateViewSet,
    NotificationViewSet, WebSocketSubscriptionViewSet,
)

# NB : /api/v1/notifications/ pointe déjà sur cette app (voir kshield/urls.py).
# On ne veut pas de doublon /notifications/notifications/, donc on registre
# le ViewSet Notification à la RACINE de cette app avec un basename explicite.
# Résultat : GET /api/v1/notifications/ (list), .../<pk>/, .../unread/, etc.

router = DefaultRouter()
router.register("templates", NotificationTemplateViewSet)
router.register("preferences", NotificationPreferenceViewSet)
router.register("subscriptions", WebSocketSubscriptionViewSet)
# Notifications à la racine — expose /api/v1/notifications/ directement.
router.register("", NotificationViewSet, basename="notification")

urlpatterns = router.urls
