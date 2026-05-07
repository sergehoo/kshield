from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    MobileBundleViewSet, MobileDeviceViewSet, OfflineScanQueueViewSet,
    PullBundleView, PushBatchView, SyncSessionViewSet,
)

router = DefaultRouter()
router.register("devices", MobileDeviceViewSet)
router.register("queue", OfflineScanQueueViewSet)
router.register("sessions", SyncSessionViewSet)
router.register("bundles", MobileBundleViewSet)

urlpatterns = [
    path("sync/push/", PushBatchView.as_view(), name="mobile-sync-push"),
    path("sync/pull/", PullBundleView.as_view(), name="mobile-sync-pull"),
] + router.urls
