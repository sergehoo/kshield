from rest_framework import serializers


def resolve_request_tenant(request):
    """Resolve the authenticated user's tenant before middleware fallbacks."""
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
            raise serializers.ValidationError("Aucun tenant associe a cet utilisateur.")
        return tenant
