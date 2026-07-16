from rest_framework import serializers

from core.tenancy import CurrentTenantDefault

from .models import (
    Badge, BadgeHelmetPairing, Camera, Device, DeviceHeartbeat,
    DeviceMaintenance, DeviceModel, FirmwareVersion, Helmet, OTAUpdate,
)


class CameraSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True, default=None)
    zone_name = serializers.CharField(source="zone.name", read_only=True, default=None)
    stream_url = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        # On n'expose JAMAIS le password en lecture.
        fields = (
            "id", "name", "site", "site_name", "zone", "zone_name",
            "location_label", "rtsp_url", "transport", "codec",
            "username",  # password = write-only via extra_kwargs
            "target_width", "target_height", "target_fps", "jpeg_quality",
            "onvif_enabled", "onvif_host", "onvif_port",
            "enable_face_recognition", "enable_motion_detection", "enable_recording",
            "status", "is_active", "last_seen_at", "last_error",
            "last_snapshot", "stream_url",
            "created_at", "updated_at",
        )
        read_only_fields = ("status", "last_seen_at", "last_error",
                             "last_snapshot", "created_at", "updated_at")
        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "rtsp_url": {"required": True},
        }

    def get_stream_url(self, obj):
        request = self.context.get("request")
        path = f"/api/v1/devices/cameras/{obj.pk}/stream.mjpg"
        return request.build_absolute_uri(path) if request else path


class DeviceModelSerializer(serializers.ModelSerializer):
    class Meta: model = DeviceModel; fields = "__all__"


class DeviceSerializer(serializers.ModelSerializer):
    class Meta: model = Device; fields = "__all__"


class BadgeSerializer(serializers.ModelSerializer):
    tenant = serializers.PrimaryKeyRelatedField(
        read_only=True,
        default=CurrentTenantDefault(),
    )
    tech = serializers.ChoiceField(
        source="type",
        choices=Badge.TYPE_CHOICES,
        required=False,
    )

    class Meta:
        model = Badge
        fields = "__all__"
        read_only_fields = (
            "tenant", "created_by", "updated_by", "created_at", "updated_at",
        )


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
