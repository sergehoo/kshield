from rest_framework import serializers

from .models import Department, Employee, EmployeeAuthorization, EmployeeContract, EmployeeSchedule, JobPosition


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta: model = Department; fields = "__all__"


class JobPositionSerializer(serializers.ModelSerializer):
    class Meta: model = JobPosition; fields = "__all__"


class EmployeeSerializer(serializers.ModelSerializer):
    """Sérializer employé.

    ``tenant`` est en read_only : il est auto-résolu côté ViewSet
    (perform_create) depuis ``request.user`` — l'API front n'a jamais
    besoin de le fournir, ce qui évite l'erreur « ce champ est obligatoire ».
    """
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = "__all__"
        read_only_fields = ("tenant",)

    def get_full_name(self, obj): return f"{obj.first_name} {obj.last_name}"


class EmployeeContractSerializer(serializers.ModelSerializer):
    class Meta: model = EmployeeContract; fields = "__all__"


class EmployeeAuthorizationSerializer(serializers.ModelSerializer):
    class Meta: model = EmployeeAuthorization; fields = "__all__"


class EmployeeScheduleSerializer(serializers.ModelSerializer):
    class Meta: model = EmployeeSchedule; fields = "__all__"
