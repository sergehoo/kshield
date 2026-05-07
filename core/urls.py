from rest_framework.routers import DefaultRouter

from .views import AddressViewSet, CompanyViewSet, FeatureFlagViewSet, TenantViewSet

router = DefaultRouter()
router.register("tenants", TenantViewSet)
router.register("companies", CompanyViewSet)
router.register("addresses", AddressViewSet)
router.register("feature-flags", FeatureFlagViewSet)

urlpatterns = router.urls
