from rest_framework import serializers

from core.tenancy import CurrentTenantDefault, resolve_request_tenant

from .models import Crew, Subcontractor, Trade, Worker, WorkerAssignment, WorkerCertification


class TradeSerializer(serializers.ModelSerializer):
    class Meta: model = Trade; fields = "__all__"


class SubcontractorSerializer(serializers.ModelSerializer):
    class Meta: model = Subcontractor; fields = "__all__"


class WorkerSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(
        read_only=True,
        default=CurrentTenantDefault(),
    )

    class Meta:
        model = Worker
        fields = "__all__"
        read_only_fields = (
            "uuid", "created_at", "updated_at", "created_by", "updated_by",
        )

    def validate(self, attrs):
        tenant = resolve_request_tenant(self.context.get("request"))
        subcontractor = attrs.get(
            "subcontractor",
            getattr(self.instance, "subcontractor", None),
        )
        if subcontractor is not None and (
            tenant is None or subcontractor.tenant_id != tenant.pk
        ):
            raise serializers.ValidationError({
                "subcontractor": "Ce sous-traitant appartient à un autre tenant."
            })
        return attrs


class WorkerCertificationSerializer(serializers.ModelSerializer):
    class Meta: model = WorkerCertification; fields = "__all__"


class CrewSerializer(serializers.ModelSerializer):
    class Meta: model = Crew; fields = "__all__"


class WorkerAssignmentSerializer(serializers.ModelSerializer):
    class Meta: model = WorkerAssignment; fields = "__all__"
