from rest_framework import serializers

from .models import Department, Employee, EmployeeAuthorization, EmployeeContract, EmployeeSchedule, JobPosition


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta: model = Department; fields = "__all__"


class JobPositionSerializer(serializers.ModelSerializer):
    class Meta: model = JobPosition; fields = "__all__"


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = "__all__"

    def get_full_name(self, obj): return f"{obj.first_name} {obj.last_name}"


class EmployeeContractSerializer(serializers.ModelSerializer):
    class Meta: model = EmployeeContract; fields = "__all__"


class EmployeeAuthorizationSerializer(serializers.ModelSerializer):
    class Meta: model = EmployeeAuthorization; fields = "__all__"


class EmployeeScheduleSerializer(serializers.ModelSerializer):
    class Meta: model = EmployeeSchedule; fields = "__all__"
