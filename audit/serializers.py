from rest_framework import serializers

from .models import AuditLog, ConformityRegister, DataExportRequest, LegalRetentionPolicy


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta: model = AuditLog; fields = "__all__"


class DataExportRequestSerializer(serializers.ModelSerializer):
    class Meta: model = DataExportRequest; fields = "__all__"


class LegalRetentionPolicySerializer(serializers.ModelSerializer):
    class Meta: model = LegalRetentionPolicy; fields = "__all__"


class ConformityRegisterSerializer(serializers.ModelSerializer):
    class Meta: model = ConformityRegister; fields = "__all__"
