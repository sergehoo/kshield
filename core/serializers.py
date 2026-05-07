from rest_framework import serializers

from .models import Address, Company, FeatureFlag, Tenant


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "uuid", "name", "code", "timezone", "currency", "is_active", "logo", "settings")
        read_only_fields = ("id", "uuid")


class CompanySerializer(serializers.ModelSerializer):
    tenant_code = serializers.CharField(source="tenant.code", read_only=True)

    class Meta:
        model = Company
        fields = (
            "id", "uuid", "tenant", "tenant_code", "name", "code", "legal_name",
            "tax_id", "sector", "contact_name", "contact_email", "contact_phone", "is_active",
        )
        read_only_fields = ("id", "uuid", "tenant_code")


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = "__all__"


class FeatureFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureFlag
        fields = ("id", "tenant", "code", "is_enabled", "description", "payload")
