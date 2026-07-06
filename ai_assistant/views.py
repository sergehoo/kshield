from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIConversation, AIMessage, AIPromptTemplate, AIToolCall
from .serializers import (
    AIChatRequestSerializer, AIConversationSerializer, AIMessageSerializer,
    AIPromptTemplateSerializer, AIToolCallSerializer,
)
from .services import AIChatService


class AIPromptTemplateViewSet(viewsets.ModelViewSet):
    queryset = AIPromptTemplate.objects.all(); serializer_class = AIPromptTemplateSerializer


class AIConversationViewSet(viewsets.ModelViewSet):
    queryset = AIConversation.objects.all(); serializer_class = AIConversationSerializer
    filterset_fields = ("tenant", "user", "is_archived")

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)
        return qs


class AIMessageViewSet(viewsets.ModelViewSet):
    queryset = AIMessage.objects.all(); serializer_class = AIMessageSerializer
    filterset_fields = ("conversation", "role")


class AIToolCallViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AIToolCall.objects.all(); serializer_class = AIToolCallSerializer
    filterset_fields = ("conversation", "tool_name", "status")


class AIChatView(APIView):
    """POST /api/v1/ai/chat — endpoint utilisé par le panel chatbot du base.html."""

    def post(self, request):
        s = AIChatRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        # Récupère ou crée la conversation
        conversation = None
        if d.get("conversation_id"):
            conversation = AIConversation.objects.filter(
                id=d["conversation_id"], user=request.user,
            ).first()
        if not conversation:
            # Résout le tenant en cascade : user.tenant → request.tenant →
            # get_current_tenant() → get_kaydan_tenant()
            from core.services import get_current_tenant, get_kaydan_tenant
            tenant = (
                getattr(request.user, "tenant", None)
                or getattr(request, "tenant", None)
                or get_current_tenant()
                or get_kaydan_tenant()
            )
            conversation = AIConversation.objects.create(
                tenant=tenant,
                user=request.user,
                title=d["message"][:80],
                site_id=d.get("site"),
            )
        AIMessage.objects.create(conversation=conversation, role="user", content=d["message"])
        reply = AIChatService.ask(
            request.user, d["message"], conversation=conversation, history=d.get("history"),
        )
        AIMessage.objects.create(conversation=conversation, role="assistant", content=reply)
        return Response({"reply": reply, "conversation_id": conversation.id})
