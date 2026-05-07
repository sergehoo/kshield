from rest_framework import serializers

from .models import (
    VisitLog, VisitPurpose, VisitRequest, Visitor, VisitorIDDocument,
    VisitorInvitation, VisitorPass, Watchlist,
)


class VisitPurposeSerializer(serializers.ModelSerializer):
    class Meta: model = VisitPurpose; fields = "__all__"


class VisitorSerializer(serializers.ModelSerializer):
    class Meta: model = Visitor; fields = "__all__"


class VisitorIDDocumentSerializer(serializers.ModelSerializer):
    class Meta: model = VisitorIDDocument; fields = "__all__"


class VisitRequestSerializer(serializers.ModelSerializer):
    class Meta: model = VisitRequest; fields = "__all__"


class VisitorInvitationSerializer(serializers.ModelSerializer):
    class Meta: model = VisitorInvitation; fields = "__all__"


class VisitorPassSerializer(serializers.ModelSerializer):
    class Meta: model = VisitorPass; fields = "__all__"


class VisitLogSerializer(serializers.ModelSerializer):
    class Meta: model = VisitLog; fields = "__all__"


class WatchlistSerializer(serializers.ModelSerializer):
    class Meta: model = Watchlist; fields = "__all__"


class WalkInCheckInSerializer(serializers.Serializer):
    site = serializers.IntegerField()
    host_employee = serializers.IntegerField(required=False)
    purpose = serializers.IntegerField(required=False)
    purpose_other = serializers.CharField(required=False, allow_blank=True)
    visitor_first_name = serializers.CharField()
    visitor_last_name = serializers.CharField()
    visitor_id_number = serializers.CharField(required=False, allow_blank=True)
    visitor_phone = serializers.CharField(required=False, allow_blank=True)
    expected_duration_minutes = serializers.IntegerField(default=60)
