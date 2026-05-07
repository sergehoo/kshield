from rest_framework.routers import DefaultRouter

from .views import (
    AttendanceCorrectionViewSet, AttendanceDayViewSet, BLEPresencePingViewSet,
    BLEPresenceWindowViewSet, LeaveRequestViewSet, OvertimeCalculationViewSet,
    OvertimeRuleViewSet, PunchViewSet, RosterViewSet,
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

urlpatterns = router.urls
