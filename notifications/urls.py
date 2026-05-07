from rest_framework.routers import DefaultRouter

from .views import (
    NotificationPreferenceViewSet, NotificationTemplateViewSet,
    NotificationViewSet, WebSocketSubscriptionViewSet,
)

router = DefaultRouter()
router.register("templates", NotificationTemplateViewSet)
router.register("preferences", NotificationPreferenceViewSet)
router.register("notifications", NotificationViewSet)
router.register("subscriptions", WebSocketSubscriptionViewSet)

urlpatterns = router.urls
