from rest_framework.routers import DefaultRouter

from .views import (
    DashboardViewSet, DashboardWidgetViewSet, ExecutiveDigestViewSet,
    KPISnapshotViewSet, ReportRunViewSet, ReportScheduleViewSet, ReportViewSet,
)

router = DefaultRouter()
router.register("reports", ReportViewSet)
router.register("runs", ReportRunViewSet)
router.register("schedules", ReportScheduleViewSet)
router.register("kpi", KPISnapshotViewSet)
router.register("dashboards", DashboardViewSet)
router.register("widgets", DashboardWidgetViewSet)
router.register("digests", ExecutiveDigestViewSet)

urlpatterns = router.urls
