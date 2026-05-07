from rest_framework import serializers

from .models import (
    AttendanceCorrection, AttendanceDay, BLEPresencePing, BLEPresenceWindow,
    LeaveRequest, OvertimeCalculation, OvertimeRule, Punch, Roster,
)


class PunchSerializer(serializers.ModelSerializer):
    class Meta: model = Punch; fields = "__all__"


class AttendanceDaySerializer(serializers.ModelSerializer):
    class Meta: model = AttendanceDay; fields = "__all__"


class BLEPresencePingSerializer(serializers.ModelSerializer):
    class Meta: model = BLEPresencePing; fields = "__all__"


class BLEPresenceWindowSerializer(serializers.ModelSerializer):
    class Meta: model = BLEPresenceWindow; fields = "__all__"


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta: model = LeaveRequest; fields = "__all__"


class RosterSerializer(serializers.ModelSerializer):
    class Meta: model = Roster; fields = "__all__"


class OvertimeRuleSerializer(serializers.ModelSerializer):
    class Meta: model = OvertimeRule; fields = "__all__"


class OvertimeCalculationSerializer(serializers.ModelSerializer):
    class Meta: model = OvertimeCalculation; fields = "__all__"


class AttendanceCorrectionSerializer(serializers.ModelSerializer):
    class Meta: model = AttendanceCorrection; fields = "__all__"
