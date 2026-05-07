from rest_framework import viewsets

from .models import Checkpoint, OpeningHours, Site, SitePolicy, Zone
from .serializers import (
    CheckpointSerializer, OpeningHoursSerializer, SitePolicySerializer,
    SiteSerializer, ZoneSerializer,
)


class SiteViewSet(viewsets.ModelViewSet):
    queryset = Site.objects.select_related("tenant", "company", "address").all()
    serializer_class = SiteSerializer
    search_fields = ("name", "code")
    filterset_fields = ("tenant", "company", "type", "status")


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.select_related("site", "parent").all()
    serializer_class = ZoneSerializer
    search_fields = ("name", "code")
    filterset_fields = ("site", "parent", "is_restricted")


class CheckpointViewSet(viewsets.ModelViewSet):
    queryset = Checkpoint.objects.select_related("site", "zone").all()
    serializer_class = CheckpointSerializer
    search_fields = ("name", "code")
    filterset_fields = ("site", "zone", "type", "mode", "is_active")


class OpeningHoursViewSet(viewsets.ModelViewSet):
    queryset = OpeningHours.objects.all()
    serializer_class = OpeningHoursSerializer
    filterset_fields = ("site", "zone", "day_of_week", "is_closed")


class SitePolicyViewSet(viewsets.ModelViewSet):
    queryset = SitePolicy.objects.all()
    serializer_class = SitePolicySerializer
    filterset_fields = ("site",)
