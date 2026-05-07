from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import APIKey, LoginAttempt, Role, RoleAssignment, User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "uuid", "email", "first_name", "last_name", "full_name",
            "phone", "photo", "tenant", "company", "is_active", "is_staff",
            "mfa_enabled", "last_login",
        )
        read_only_fields = ("id", "uuid", "is_staff", "last_login", "full_name")

    def get_full_name(self, obj): return obj.get_full_name() or obj.email


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=10)

    class Meta:
        model = User
        fields = ("email", "password", "first_name", "last_name", "phone", "tenant", "company")

    def create(self, validated):
        password = validated.pop("password")
        user = User(**validated)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    mfa_code = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        user = authenticate(email=data["email"], password=data["password"])
        if not user:
            raise serializers.ValidationError("Identifiants invalides")
        if not user.is_active:
            raise serializers.ValidationError("Compte désactivé")
        if user.mfa_enabled and not data.get("mfa_code"):
            raise serializers.ValidationError("Code MFA requis")
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(many=True, read_only=True, slug_field="code")

    class Meta:
        model = Role
        fields = ("id", "code", "name", "scope", "description", "is_system", "permissions")


class RoleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleAssignment
        fields = ("id", "user", "role", "site", "granted_at")
        read_only_fields = ("granted_at",)


class APIKeySerializer(serializers.ModelSerializer):
    secret = serializers.CharField(read_only=True, required=False)

    class Meta:
        model = APIKey
        fields = (
            "id", "name", "scope", "tenant", "site", "public_id",
            "is_active", "expires_at", "last_used_at", "created_at", "revoked_at", "secret",
        )
        read_only_fields = ("public_id", "last_used_at", "created_at", "revoked_at")


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = "__all__"
