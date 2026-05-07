from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AccessDecisionViewSet, AccessEventViewSet, AccessRuleViewSet,
    DoorCommandViewSet, QRCodeTokenViewSet, ScanView,
)

router = DefaultRouter()
router.register("events", AccessEventViewSet)
router.register("rules", AccessRuleViewSet)
router.register("decisions", AccessDecisionViewSet)
router.register("door-commands", DoorCommandViewSet)
router.register("qr-tokens", QRCodeTokenViewSet)

urlpatterns = [path("scan/", ScanView.as_view(), name="access-scan")] + router.urls
