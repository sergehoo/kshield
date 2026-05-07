from rest_framework.routers import DefaultRouter

from .views import (
    DepartmentViewSet, EmployeeAuthorizationViewSet, EmployeeContractViewSet,
    EmployeeScheduleViewSet, EmployeeViewSet, JobPositionViewSet,
)

router = DefaultRouter()
router.register("departments", DepartmentViewSet)
router.register("positions", JobPositionViewSet)
router.register("employees", EmployeeViewSet)
router.register("contracts", EmployeeContractViewSet)
router.register("authorizations", EmployeeAuthorizationViewSet)
router.register("schedules", EmployeeScheduleViewSet)

urlpatterns = router.urls
