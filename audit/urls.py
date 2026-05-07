from rest_framework.routers import DefaultRouter

from .views import (
    AuditLogViewSet, ConformityRegisterViewSet,
    DataExportRequestViewSet, LegalRetentionPolicyViewSet,
)

router = DefaultRouter()
router.register("logs", AuditLogViewSet)
router.register("exports", DataExportRequestViewSet)
router.register("retention-policies", LegalRetentionPolicyViewSet)
router.register("conformity", ConformityRegisterViewSet)

urlpatterns = router.urls
