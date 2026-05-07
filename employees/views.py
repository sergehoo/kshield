from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Department, Employee, EmployeeAuthorization, EmployeeContract, EmployeeSchedule, JobPosition
from .serializers import (
    DepartmentSerializer, EmployeeAuthorizationSerializer, EmployeeContractSerializer,
    EmployeeScheduleSerializer, EmployeeSerializer, JobPositionSerializer,
)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("company", "parent").all()
    serializer_class = DepartmentSerializer
    search_fields = ("name", "code")
    filterset_fields = ("company", "parent")


class JobPositionViewSet(viewsets.ModelViewSet):
    queryset = JobPosition.objects.all()
    serializer_class = JobPositionSerializer
    search_fields = ("title", "code")
    filterset_fields = ("company",)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related(
        "tenant", "company", "department", "position", "manager",
    ).prefetch_related("authorized_sites").all()
    serializer_class = EmployeeSerializer
    search_fields = ("matricule", "first_name", "last_name", "email", "phone")
    filterset_fields = ("tenant", "company", "department", "status", "contract_type")

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        emp = self.get_object()
        emp.status = "terminated"
        emp.save(update_fields=["status"])
        return Response({"status": emp.status})


class EmployeeContractViewSet(viewsets.ModelViewSet):
    queryset = EmployeeContract.objects.select_related("employee").all()
    serializer_class = EmployeeContractSerializer
    filterset_fields = ("employee", "contract_type")


class EmployeeAuthorizationViewSet(viewsets.ModelViewSet):
    queryset = EmployeeAuthorization.objects.select_related("employee", "zone").all()
    serializer_class = EmployeeAuthorizationSerializer
    filterset_fields = ("employee", "zone")


class EmployeeScheduleViewSet(viewsets.ModelViewSet):
    queryset = EmployeeSchedule.objects.select_related("employee").all()
    serializer_class = EmployeeScheduleSerializer
    filterset_fields = ("employee", "day_of_week", "shift")
