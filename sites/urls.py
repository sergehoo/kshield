from rest_framework.routers import DefaultRouter

from .views import (
    CheckpointViewSet, OpeningHoursViewSet, SitePolicyViewSet, SiteViewSet, ZoneViewSet,
)

router = DefaultRouter()
router.register("sites", SiteViewSet)
router.register("zones", ZoneViewSet)
router.register("checkpoints", CheckpointViewSet)
router.register("opening-hours", OpeningHoursViewSet)
router.register("policies", SitePolicyViewSet)

urlpatterns = router.urls
