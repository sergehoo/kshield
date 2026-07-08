import secrets
import hashlib

from django.contrib.auth.hashers import make_password
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import APIKey, LoginAttempt, Role, RoleAssignment, User
from .serializers import (
    APIKeySerializer, LoginAttemptSerializer, LoginSerializer, RoleAssignmentSerializer,
    RoleSerializer, UserCreateSerializer, UserSerializer,
)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        import logging
        import traceback
        logger = logging.getLogger("accounts.login")

        serializer = LoginSerializer(data=request.data)
        try:
            success = serializer.is_valid()
        except Exception as exc:
            # LoginSerializer.validate() peut lever une exception non-DRF si
            # authenticate() ou RefreshToken.for_user() plantent. On log au lieu
            # de laisser Django renvoyer une 500 opaque.
            logger.exception("LoginView: is_valid() a levé une exception : %s", exc)
            return Response(
                {"detail": "Erreur interne du service d'authentification.",
                 "error_type": type(exc).__name__,
                 "error_message": str(exc)[:300]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Log LoginAttempt en best-effort (ne doit jamais bloquer le login)
        try:
            LoginAttempt.objects.create(
                email=request.data.get("email", ""),
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                success=success,
                reason="" if success else str(serializer.errors)[:120],
            )
        except Exception:
            logger.exception("LoginView: échec création LoginAttempt (non bloquant)")

        if not success:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            return Response(serializer.validated_data)
        except Exception as exc:
            logger.exception("LoginView: erreur sérialisation validated_data : %s", exc)
            return Response(
                {"detail": "Login OK mais erreur de sérialisation de la réponse.",
                 "error_type": type(exc).__name__,
                 "error_message": str(exc)[:300]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("tenant", "company").all()
    search_fields = ("email", "first_name", "last_name", "phone")
    filterset_fields = ("tenant", "company", "is_active", "is_staff")

    def get_serializer_class(self):
        return UserCreateSerializer if self.action == "create" else UserSerializer


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.prefetch_related("permissions").all()
    serializer_class = RoleSerializer
    search_fields = ("code", "name")


class RoleAssignmentViewSet(viewsets.ModelViewSet):
    queryset = RoleAssignment.objects.select_related("user", "role", "site").all()
    serializer_class = RoleAssignmentSerializer
    filterset_fields = ("user", "role", "site")


class APIKeyViewSet(viewsets.ModelViewSet):
    queryset = APIKey.objects.select_related("tenant", "site").all()
    serializer_class = APIKeySerializer
    filterset_fields = ("tenant", "site", "scope", "is_active")

    def perform_create(self, serializer):
        public_id = secrets.token_urlsafe(12)
        secret = APIKey.generate_secret()
        serializer.save(
            public_id=public_id,
            secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        )
        # secret renvoyé une seule fois en sortie
        serializer.instance._plain_secret = secret  # type: ignore[attr-defined]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        instance = self.get_queryset().get(pk=response.data["id"])
        plain = getattr(instance, "_plain_secret", None)
        if plain:
            response.data["secret"] = plain
        return response

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        from django.utils import timezone
        key = self.get_object()
        key.is_active = False
        key.revoked_at = timezone.now()
        key.save(update_fields=["is_active", "revoked_at"])
        return Response({"status": "revoked"})


class LoginAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LoginAttempt.objects.all()
    serializer_class = LoginAttemptSerializer
    filterset_fields = ("email", "success")
