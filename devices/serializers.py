from rest_framework import serializers

from .models import (
    Badge, BadgeHelmetPairing, Device, DeviceHeartbeat, DeviceMaintenance,
    DeviceModel, FirmwareVersion, Helmet, OTAUpdate,
)


class DeviceModelSerializer(serializers.ModelSerializer):
    class Meta: model = DeviceModel; fields = "__all__"


class DeviceSerializer(serializers.ModelSerializer):
    class Meta: model = Device; fields = "__all__"


class BadgeSerializer(serializers.ModelSerializer):
    class Meta: model = Badge; fields = "__all__"


class HelmetSerializer(serializers.ModelSerializer):
    class Meta: model = Helmet; fields = "__all__"


class BadgeHelmetPairingSerializer(serializers.ModelSerializer):
    class Meta: model = BadgeHelmetPairing; fields = "__all__"


class DeviceHeartbeatSerializer(serializers.ModelSerializer):
    class Meta: model = DeviceHeartbeat; fields = "__all__"


class DeviceMaintenanceSerializer(serializers.ModelSerializer):
    class Meta: model = DeviceMaintenance; fields = "__all__"


class FirmwareVersionSerializer(serializers.ModelSerializer):
    class Meta: model = FirmwareVersion; fields = "__all__"


class OTAUpdateSerializer(serializers.ModelSerializer):
    class Meta: model = OTAUpdate; fields = "__all__"
