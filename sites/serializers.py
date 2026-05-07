from rest_framework import serializers

from .models import Checkpoint, OpeningHours, Site, SitePolicy, Zone


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = "__all__"


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = "__all__"


class CheckpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = Checkpoint
        fields = "__all__"


class OpeningHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = OpeningHours
        fields = "__all__"


class SitePolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = SitePolicy
        fields = "__all__"
