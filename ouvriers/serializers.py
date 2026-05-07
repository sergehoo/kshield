from rest_framework import serializers

from .models import Crew, Subcontractor, Trade, Worker, WorkerAssignment, WorkerCertification


class TradeSerializer(serializers.ModelSerializer):
    class Meta: model = Trade; fields = "__all__"


class SubcontractorSerializer(serializers.ModelSerializer):
    class Meta: model = Subcontractor; fields = "__all__"


class WorkerSerializer(serializers.ModelSerializer):
    class Meta: model = Worker; fields = "__all__"


class WorkerCertificationSerializer(serializers.ModelSerializer):
    class Meta: model = WorkerCertification; fields = "__all__"


class CrewSerializer(serializers.ModelSerializer):
    class Meta: model = Crew; fields = "__all__"


class WorkerAssignmentSerializer(serializers.ModelSerializer):
    class Meta: model = WorkerAssignment; fields = "__all__"
