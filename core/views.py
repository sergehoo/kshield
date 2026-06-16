from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, viewsets

from .models import Address, Company, FeatureFlag, Tenant
from .serializers import AddressSerializer, CompanySerializer, FeatureFlagSerializer, TenantSerializer


@csrf_exempt
@never_cache
def healthz(request):
    """Endpoint healthcheck public — utilisé par Docker HEALTHCHECK.

    Pas de DB query, pas de cache. Retourne 200 si Django répond.
    Volontairement minimaliste pour rester rapide.
    """
    return JsonResponse({"status": "ok"}, status=200)


@csrf_exempt
@never_cache
def readyz(request):
    """Endpoint readiness — vérifie aussi DB + cache.

    Différent de healthz qui sert juste à dire 'le process est vivant'.
    """
    from django.db import connection
    from django.core.cache import cache

    checks = {"db": False, "cache": False}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            checks["db"] = True
    except Exception as exc:
        checks["db_error"] = str(exc)[:200]
    try:
        cache.set("readyz_ping", 1, 5)
        checks["cache"] = bool(cache.get("readyz_ping"))
    except Exception as exc:
        checks["cache_error"] = str(exc)[:200]

    ok = checks["db"] and checks["cache"]
    return JsonResponse({"status": "ok" if ok else "degraded", **checks},
                          status=200 if ok else 503)


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
