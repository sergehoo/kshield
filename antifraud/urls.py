from rest_framework.routers import DefaultRouter

from .views import (
    BLEStillnessSignalViewSet, FraudAlertViewSet, FraudInvestigationViewSet,
    FraudRuleViewSet, FraudScoringViewSet,
)

router = DefaultRouter()
router.register("rules", FraudRuleViewSet)
router.register("alerts", FraudAlertViewSet)
router.register("investigations", FraudInvestigationViewSet)
router.register("scoring", FraudScoringViewSet)
router.register("stillness", BLEStillnessSignalViewSet)

urlpatterns = router.urls
