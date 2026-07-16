from rest_framework import serializers

from .models import Crew, Subcontractor, Trade, Worker, WorkerAssignment, WorkerCertification


def resolve_request_tenant(request):
    """Résout le tenant du user avant le fallback posé par le middleware."""
    user = getattr(request, "user", None)
    tenant = getattr(user, "tenant", None)
    if tenant is not None:
        return tenant
    company = getattr(user, "company", None)
    if company is not None and company.tenant_id:
        return company.tenant
    return getattr(request, "tenant", None)


class CurrentTenantDefault:
    requires_context = True

    def __call__(self, serializer_field):
        request = serializer_field.context.get("request")
        tenant = resolve_request_tenant(request)
        if tenant is None:
            raise serializers.ValidationError("Aucun tenant associé à cet utilisateur.")
        return tenant


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
