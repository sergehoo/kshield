from rest_framework import permissions, viewsets

from .models import Address, Company, FeatureFlag, Tenant
from .serializers import AddressSerializer, CompanySerializer, FeatureFlagSerializer, TenantSerializer


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    search_fields = ("name", "code")
    filterset_fields = ("is_active",)


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.select_related("tenant").all()
    serializer_class = CompanySerializer
    search_fields = ("name", "code", "legal_name")
    filterset_fields = ("tenant", "sector", "is_active")


class AddressViewSet(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer


class FeatureFlagViewSet(viewsets.ModelViewSet):
    queryset = FeatureFlag.objects.select_related("tenant").all()
    serializer_class = FeatureFlagSerializer
    search_fields = ("code",)
    filterset_fields = ("tenant", "is_enabled")
