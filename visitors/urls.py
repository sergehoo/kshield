from rest_framework.routers import DefaultRouter

from .views import (
    VisitLogViewSet, VisitPurposeViewSet, VisitRequestViewSet, VisitorIDDocumentViewSet,
    VisitorInvitationViewSet, VisitorPassViewSet, VisitorViewSet, WatchlistViewSet,
)

router = DefaultRouter()
router.register("purposes", VisitPurposeViewSet)
router.register("visitors", VisitorViewSet)
router.register("id-documents", VisitorIDDocumentViewSet)
router.register("requests", VisitRequestViewSet)
router.register("invitations", VisitorInvitationViewSet)
router.register("passes", VisitorPassViewSet)
router.register("logs", VisitLogViewSet)
router.register("watchlist", WatchlistViewSet)

urlpatterns = router.urls
