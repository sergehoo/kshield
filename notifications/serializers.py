from rest_framework import serializers

from .models import Notification, NotificationPreference, NotificationTemplate, WebSocketSubscription


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta: model = NotificationTemplate; fields = "__all__"


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta: model = NotificationPreference; fields = "__all__"


class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model = Notification; fields = "__all__"


class WebSocketSubscriptionSerializer(serializers.ModelSerializer):
    class Meta: model = WebSocketSubscription; fields = "__all__"
