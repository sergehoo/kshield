from rest_framework import serializers

from .models import AIConversation, AIMessage, AIPromptTemplate, AIToolCall


class AIPromptTemplateSerializer(serializers.ModelSerializer):
    class Meta: model = AIPromptTemplate; fields = "__all__"


class AIConversationSerializer(serializers.ModelSerializer):
    class Meta: model = AIConversation; fields = "__all__"


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta: model = AIMessage; fields = "__all__"


class AIToolCallSerializer(serializers.ModelSerializer):
    class Meta: model = AIToolCall; fields = "__all__"


class AIChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()
    conversation_id = serializers.IntegerField(required=False)
    history = serializers.ListField(child=serializers.DictField(), required=False)
    site = serializers.IntegerField(required=False)
