from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    APIKeyViewSet, LoginAttemptViewSet, LoginView, MeView,
    RoleAssignmentViewSet, RoleViewSet, UserViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("roles", RoleViewSet)
router.register("role-assignments", RoleAssignmentViewSet)
router.register("api-keys", APIKeyViewSet)
router.register("login-attempts", LoginAttemptViewSet)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),
] + router.urls
