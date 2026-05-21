from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DepartmentViewSet, EmployeeAuthorizationViewSet, EmployeeContractViewSet,
    EmployeeScheduleViewSet, EmployeeViewSet, FaceEngineStatusAPIView,
    FaceEnrollAPIView, FaceMatchAPIView, JobPositionViewSet,
)

router = DefaultRouter()
router.register("departments", DepartmentViewSet)
router.register("positions", JobPositionViewSet)
router.register("employees", EmployeeViewSet)
router.register("contracts", EmployeeContractViewSet)
router.register("authorizations", EmployeeAuthorizationViewSet)
router.register("schedules", EmployeeScheduleViewSet)

urlpatterns = [
    path("face/enroll/", FaceEnrollAPIView.as_view(),        name="face-enroll"),
    path("face/match/",  FaceMatchAPIView.as_view(),         name="face-match"),
    path("face/status/", FaceEngineStatusAPIView.as_view(),  name="face-status"),
] + router.urls
