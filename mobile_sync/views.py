from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from access_control.services import AccessGatewayService

from .models import MobileBundle, MobileDevice, OfflineScanQueue, SyncSession
from .serializers import (
    MobileBundleSerializer, MobileDeviceSerializer, OfflineScanQueueSerializer,
    PushBatchSerializer, SyncSessionSerializer,
)


class MobileDeviceViewSet(viewsets.ModelViewSet):
    queryset = MobileDevice.objects.all(); serializer_class = MobileDeviceSerializer
    filterset_fields = ("tenant", "user", "site", "status", "os")
    search_fields = ("device_id", "name")


class OfflineScanQueueViewSet(viewsets.ModelViewSet):
    queryset = OfflineScanQueue.objects.all(); serializer_class = OfflineScanQueueSerializer
    filterset_fields = ("device", "status")


class SyncSessionViewSet(viewsets.ModelViewSet):
    queryset = SyncSession.objects.all(); serializer_class = SyncSessionSerializer
    filterset_fields = ("device",)


class MobileBundleViewSet(viewsets.ModelViewSet):
    queryset = MobileBundle.objects.all(); serializer_class = MobileBundleSerializer
    filterset_fields = ("device",)


class PushBatchView(APIView):
    """POST /api/v1/mobile/sync/push — terminal pousse ses scans offline."""

    def post(self, request):
        s = PushBatchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        device = MobileDevice.objects.filter(device_id=s.validated_data["device_id"]).first()
        if not device:
            return Response({"detail": "device unknown"}, status=status.HTTP_404_NOT_FOUND)

        synced, duplicates, rejected = 0, 0, 0
        for item in s.validated_data["items"]:
            client_uuid = item.get("client_uuid")
            existing = OfflineScanQueue.objects.filter(client_uuid=client_uuid).first() if client_uuid else None
            if existing:
                duplicates += 1; continue
            q = OfflineScanQueue.objects.create(
                device=device,
                payload=item,
                captured_at=item.get("captured_at") or timezone.now(),
                status="pending",
                client_uuid=client_uuid or None,
            )
            try:
                event = AccessGatewayService.process_scan(item)
                q.status = "synced"
                q.synced_at = timezone.now()
                q.resulting_event_id = event.id
                q.save()
                synced += 1
            except Exception as exc:
                q.status = "rejected"
                q.rejection_reason = str(exc)[:240]
                q.save()
                rejected += 1

        device.last_sync_at = timezone.now()
        device.save(update_fields=["last_sync_at"])
        return Response({"synced": synced, "duplicates": duplicates, "rejected": rejected})


class PullBundleView(APIView):
    """POST /api/v1/mobile/sync/pull — terminal récupère son delta."""

    def post(self, request):
        device_id = request.data.get("device_id")
        device = MobileDevice.objects.filter(device_id=device_id).first()
        if not device:
            return Response({"detail": "device unknown"}, status=status.HTTP_404_NOT_FOUND)
        # bundle minimal — à enrichir (badges autorisés, watchlist, règles, ...)
        bundle = MobileBundle.objects.create(
            device=device,
            since=device.last_sync_at or timezone.now(),
            payload={"badges": [], "rules": [], "watchlist": []},
            delivered_at=timezone.now(),
        )
        return Response(MobileBundleSerializer(bundle).data)
