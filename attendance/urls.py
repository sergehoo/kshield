from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceCorrectionViewSet, AttendanceDayViewSet, BLEPresencePingViewSet,
    BLEPresenceWindowViewSet, LeaveRequestViewSet, OvertimeCalculationViewSet,
    OvertimeRuleViewSet, PunchViewSet, RosterViewSet,
    AttendanceSummaryView, AttendancePresenceLiveView,
)

router = DefaultRouter()
router.register("punches", PunchViewSet)
router.register("days", AttendanceDayViewSet)
router.register("ble-pings", BLEPresencePingViewSet)
router.register("ble-windows", BLEPresenceWindowViewSet)
router.register("leaves", LeaveRequestViewSet)
router.register("rosters", RosterViewSet)
router.register("overtime-rules", OvertimeRuleViewSet)
router.register("overtime", OvertimeCalculationViewSet)
router.register("corrections", AttendanceCorrectionViewSet)

urlpatterns = [
    # KPIs dashboard React
    path("summary/today/", AttendanceSummaryView.as_view(), name="attendance-summary-today"),
    path("presence/live/", AttendancePresenceLiveView.as_view(), name="attendance-presence-live"),
] + router.urls
