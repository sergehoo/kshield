from django.contrib import admin

from .models import AIConversation, AIMessage, AIPromptTemplate, AIToolCall


@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "site", "started_at", "last_activity_at", "is_archived")
    list_filter = ("is_archived", "site")


admin.site.register([AIPromptTemplate, AIMessage, AIToolCall])
