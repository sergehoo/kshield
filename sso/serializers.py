"""Serializers DRF pour les modèles SSO (mobile + intégrations)."""
from __future__ import annotations

from rest_framework import serializers


class SSOIdentitySerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        from sso.models import SSOIdentity
        model = SSOIdentity
        fields = (
            "id", "subject", "issuer", "preferred_username",
            "email_verified", "federation_provider",
            "last_login_ip", "last_synced_at",
            "user", "user_email", "user_full_name",
        )
        read_only_fields = fields

    def get_user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.email


class SSOLoginAuditSerializer(serializers.ModelSerializer):
    class Meta:
        from sso.models import SSOLoginAudit
        model = SSOLoginAudit
        fields = "__all__"
        read_only_fields = fields


class OfflineUserCacheSerializer(serializers.ModelSerializer):
    class Meta:
        from sso.models import OfflineUserCredentialCache
        model = OfflineUserCredentialCache
        fields = ("id", "user", "site", "is_active",
                   "permissions_snapshot", "expires_at", "cached_at")
        read_only_fields = ("cached_at",)
