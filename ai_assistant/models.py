"""KAYDAN SHIELD — ai_assistant: conversations, messages, tool calls."""
import uuid

from django.db import models

from core.models import TimeStampedModel


class AIPromptTemplate(TimeStampedModel):
    code = models.SlugField(max_length=80, unique=True)
    role = models.CharField(max_length=80, blank=True, help_text="ex: rh, controleur, gardien")
    name = models.CharField(max_length=180)
    system_prompt = models.TextField()
    is_active = models.BooleanField(default=True)


class AIConversation(TimeStampedModel):
    tenant = models.ForeignKey("core.Tenant", on_delete=models.CASCADE, related_name="ai_conversations")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="ai_conversations")
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=240, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    site = models.ForeignKey(
        "sites.Site", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ai_conversations",
    )
    context = models.JSONField(default=dict, blank=True)
    is_archived = models.BooleanField(default=False)


class AIMessage(TimeStampedModel):
    ROLE_CHOICES = [
        ("system", "Système"), ("user", "Utilisateur"),
        ("assistant", "Assistant"), ("tool", "Outil"),
    ]
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=80, blank=True)


class AIToolCall(TimeStampedModel):
    STATUS_CHOICES = [
        ("queued", "En file"), ("running", "En cours"),
        ("succeeded", "Réussi"), ("failed", "Échec"),
    ]
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name="tool_calls")
    message = models.ForeignKey(
        AIMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="tool_calls",
    )
    tool_name = models.CharField(max_length=120)
    arguments = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="queued")
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
