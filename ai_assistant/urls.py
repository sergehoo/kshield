from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AIChatView, AIConversationViewSet, AIMessageViewSet,
    AIPromptTemplateViewSet, AIToolCallViewSet,
)

router = DefaultRouter()
router.register("templates", AIPromptTemplateViewSet)
router.register("conversations", AIConversationViewSet)
router.register("messages", AIMessageViewSet)
router.register("tool-calls", AIToolCallViewSet)

urlpatterns = [
    path("chat", AIChatView.as_view(), name="ai-chat"),
] + router.urls
