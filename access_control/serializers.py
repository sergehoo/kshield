from rest_framework import serializers

from .models import AccessDecision, AccessEvent, AccessRule, DoorCommand, QRCodeToken


class AccessEventSerializer(serializers.ModelSerializer):
    class Meta: model = AccessEvent; fields = "__all__"


class AccessRuleSerializer(serializers.ModelSerializer):
    class Meta: model = AccessRule; fields = "__all__"


class AccessDecisionSerializer(serializers.ModelSerializer):
    class Meta: model = AccessDecision; fields = "__all__"


class DoorCommandSerializer(serializers.ModelSerializer):
    class Meta: model = DoorCommand; fields = "__all__"


class QRCodeTokenSerializer(serializers.ModelSerializer):
    class Meta: model = QRCodeToken; fields = "__all__"


class ScanSerializer(serializers.Serializer):
    """Payload reçu d'un terminal lors d'un scan."""

    device_serial = serializers.CharField()
    timestamp = serializers.DateTimeField()
    badge_uid = serializers.CharField(required=False, allow_blank=True)
    helmet_uid = serializers.CharField(required=False, allow_blank=True)
    qr_token = serializers.CharField(required=False, allow_blank=True)
    method = serializers.ChoiceField(choices=AccessEvent.METHOD_CHOICES, default="nfc")
    direction = serializers.ChoiceField(choices=AccessEvent.DIRECTION_CHOICES, default="in")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    raw_payload = serializers.JSONField(required=False)
