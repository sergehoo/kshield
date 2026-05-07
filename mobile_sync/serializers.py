from rest_framework import serializers

from .models import MobileBundle, MobileDevice, OfflineScanQueue, SyncSession


class MobileDeviceSerializer(serializers.ModelSerializer):
    class Meta: model = MobileDevice; fields = "__all__"


class OfflineScanQueueSerializer(serializers.ModelSerializer):
    class Meta: model = OfflineScanQueue; fields = "__all__"


class SyncSessionSerializer(serializers.ModelSerializer):
    class Meta: model = SyncSession; fields = "__all__"


class MobileBundleSerializer(serializers.ModelSerializer):
    class Meta: model = MobileBundle; fields = "__all__"


class PushBatchSerializer(serializers.Serializer):
    device_id = serializers.CharField()
    items = serializers.ListField(child=serializers.JSONField())
