from rest_framework import viewsets

from .models import (
    AttendanceCorrection, AttendanceDay, BLEPresencePing, BLEPresenceWindow,
    LeaveRequest, OvertimeCalculation, OvertimeRule, Punch, Roster,
)
from .serializers import (
    AttendanceCorrectionSerializer, AttendanceDaySerializer, BLEPresencePingSerializer,
    BLEPresenceWindowSerializer, LeaveRequestSerializer, OvertimeCalculationSerializer,
    OvertimeRuleSerializer, PunchSerializer, RosterSerializer,
)


class PunchViewSet(viewsets.ModelViewSet):
    queryset = Punch.objects.select_related("site", "source_event").all()
    serializer_class = PunchSerializer
    filterset_fields = ("tenant", "site", "type", "status", "holder_kind")
    ordering_fields = ("timestamp",)


class AttendanceDayViewSet(viewsets.ModelViewSet):
    queryset = AttendanceDay.objects.select_related("site").all()
    serializer_class = AttendanceDaySerializer
    filterset_fields = ("tenant", "site", "status", "date", "holder_kind")


class BLEPresencePingViewSet(viewsets.ModelViewSet):
    queryset = BLEPresencePing.objects.select_related("helmet", "zone").all()
    serializer_class = BLEPresencePingSerializer
    filterset_fields = ("helmet", "zone", "is_immobile")


class BLEPresenceWindowViewSet(viewsets.ModelViewSet):
    queryset = BLEPresenceWindow.objects.all(); serializer_class = BLEPresenceWindowSerializer
    filterset_fields = ("helmet", "zone")


class LeaveRequestViewSet(viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.all(); serializer_class = LeaveRequestSerializer
    filterset_fields = ("employee", "worker", "type", "status")


class RosterViewSet(viewsets.ModelViewSet):
    queryset = Roster.objects.all(); serializer_class = RosterSerializer
    filterset_fields = ("tenant", "site", "date", "holder_kind")


class OvertimeRuleViewSet(viewsets.ModelViewSet):
    queryset = OvertimeRule.objects.all(); serializer_class = OvertimeRuleSerializer
    filterset_fields = ("company", "is_active")


class OvertimeCalculationViewSet(viewsets.ModelViewSet):
    queryset = OvertimeCalculation.objects.all(); serializer_class = OvertimeCalculationSerializer
    filterset_fields = ("employee", "worker", "week_start")


class AttendanceCorrectionViewSet(viewsets.ModelViewSet):
    queryset = AttendanceCorrection.objects.all(); serializer_class = AttendanceCorrectionSerializer
    filterset_fields = ("attendance_day", "performed_by")
