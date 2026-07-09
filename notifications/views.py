from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification, NotificationPreference, NotificationTemplate, WebSocketSubscription
from .serializers import (
    NotificationPreferenceSerializer, NotificationSerializer,
    NotificationTemplateSerializer, WebSocketSubscriptionSerializer,
)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.all(); serializer_class = NotificationTemplateSerializer
    filterset_fields = ("tenant", "channel", "is_active")
    search_fields = ("code", "subject")


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    queryset = NotificationPreference.objects.all(); serializer_class = NotificationPreferenceSerializer
    filterset_fields = ("user", "channel", "template_code", "is_enabled")


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all(); serializer_class = NotificationSerializer
    filterset_fields = ("tenant", "recipient", "channel", "status")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            qs = qs.filter(recipient=self.request.user)
        return qs

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.read_at = timezone.now()
        notif.status = "read"
        notif.save(update_fields=["read_at", "status"])
        return Response(NotificationSerializer(notif).data)

    # ─── Endpoints consommés par la topbar React ────────────────
    @action(detail=False, methods=["get"], url_path="unread")
    def unread(self, request):
        """Notifs non lues du user courant + count.

        GET /api/v1/notifications/notifications/unread/ → { count, results }
        Alias exposé aussi à /api/v1/notifications/unread/ via kshield/urls.py.
        """
        qs = self.get_queryset().filter(read_at__isnull=True).order_by("-created_at")
        top = qs[:20]
        return Response({
            "count": qs.count(),
            "results": NotificationSerializer(top, many=True).data,
        })

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        """Marque toutes les notifications non lues du user comme lues."""
        updated = self.get_queryset().filter(read_at__isnull=True).update(
            read_at=timezone.now(), status="read",
        )
        return Response({"marked_read": updated})

    @action(detail=True, methods=["post"], url_path="read")
    def read_alias(self, request, pk=None):
        """Alias court pour /mark-read/ — utilisé par le front React."""
        return self.mark_read(request, pk=pk)


class WebSocketSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = WebSocketSubscription.objects.all(); serializer_class = WebSocketSubscriptionSerializer
    filterset_fields = ("user", "topic")
