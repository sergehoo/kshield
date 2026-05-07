from rest_framework.routers import DefaultRouter

from .views import (
    CrewViewSet, SubcontractorViewSet, TradeViewSet, WorkerAssignmentViewSet,
    WorkerCertificationViewSet, WorkerViewSet,
)

router = DefaultRouter()
router.register("trades", TradeViewSet)
router.register("subcontractors", SubcontractorViewSet)
router.register("workers", WorkerViewSet)
router.register("certifications", WorkerCertificationViewSet)
router.register("crews", CrewViewSet)
router.register("assignments", WorkerAssignmentViewSet)

urlpatterns = router.urls
