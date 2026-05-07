from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BadgeHelmetPairingViewSet, BadgeIssueWorkflowAPIView,
    BadgeLookupAPIView, BadgeLostAPIView,
    BadgeReactivateAPIView, BadgeReleaseAPIView, BadgeRevokeAPIView,
    BadgeSuspendAPIView, BadgeViewSet,
    DeviceHeartbeatViewSet, DeviceMaintenanceViewSet, DeviceModelViewSet,
    DeviceViewSet, FirmwareVersionViewSet, HelmetViewSet, OTAUpdateViewSet,
)

router = DefaultRouter()
router.register("models", DeviceModelViewSet)
router.register("devices", DeviceViewSet)
router.register("badges", BadgeViewSet)
router.register("helmets", HelmetViewSet)
router.register("pairings", BadgeHelmetPairingViewSet)
router.register("heartbeats", DeviceHeartbeatViewSet)
router.register("maintenances", DeviceMaintenanceViewSet)
router.register("firmwares", FirmwareVersionViewSet)
router.register("ota", OTAUpdateViewSet)

urlpatterns = [
    path("badges/issue/",                 BadgeIssueWorkflowAPIView.as_view(), name="badge-issue"),
    path("badges/lookup/",                BadgeLookupAPIView.as_view(),        name="badge-lookup"),
    path("badges/<int:pk>/release/",      BadgeReleaseAPIView.as_view(),       name="badge-release"),
    path("badges/<int:pk>/suspend/",      BadgeSuspendAPIView.as_view(),       name="badge-suspend"),
    path("badges/<int:pk>/reactivate/",   BadgeReactivateAPIView.as_view(),    name="badge-reactivate"),
    path("badges/<int:pk>/revoke/",       BadgeRevokeAPIView.as_view(),        name="badge-revoke"),
    path("badges/<int:pk>/mark-lost/",    BadgeLostAPIView.as_view(),          name="badge-lost"),
] + router.urls
