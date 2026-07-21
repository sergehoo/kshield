from rest_framework import serializers

from .models import AccessDecision, AccessEvent, AccessRule, DoorCommand, QRCodeToken


class AccessDecisionSerializer(serializers.ModelSerializer):
    class Meta: model = AccessDecision; fields = "__all__"


class DoorCommandSerializer(serializers.ModelSerializer):
    command_label = serializers.CharField(source="get_command_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta: model = DoorCommand; fields = "__all__"


class AccessEventSerializer(serializers.ModelSerializer):
    """Événement enrichi pour les vues opérateur et le flux temps réel."""

    holder_name = serializers.SerializerMethodField()
    holder_detail = serializers.SerializerMethodField()
    device_detail = serializers.SerializerMethodField()
    site_detail = serializers.SerializerMethodField()
    zone_detail = serializers.SerializerMethodField()
    checkpoint_detail = serializers.SerializerMethodField()
    operator_detail = serializers.SerializerMethodField()
    direction_label = serializers.CharField(source="get_direction_display", read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    decision_label = serializers.CharField(source="get_decision_display", read_only=True)
    holder_kind_label = serializers.CharField(source="get_holder_kind_display", read_only=True)
    processing_delay_ms = serializers.SerializerMethodField()

    class Meta:
        model = AccessEvent
        fields = "__all__"

    def get_holder_name(self, obj):
        detail = self.get_holder_detail(obj)
        return detail["name"] if detail else None

    def get_holder_detail(self, obj):
        holder = obj.holder
        if holder is None:
            return None

        name = self._person_name(holder)
        detail = {
            "id": holder.pk,
            "kind": obj.holder_kind,
            "kind_label": obj.get_holder_kind_display(),
            "name": name,
            "reference": self._first_value(holder, "matricule", "id_number", "id_document_number"),
            "photo_url": self._media_url(getattr(holder, "photo", None)),
            "status": getattr(holder, "status", None),
            "role": None,
            "organization": None,
        }

        if obj.holder_kind == "employee":
            detail["role"] = self._related_label(getattr(holder, "position", None), "title")
            detail["organization"] = self._related_label(getattr(holder, "department", None), "name")
        elif obj.holder_kind == "worker":
            detail["role"] = self._related_label(getattr(holder, "trade", None), "name")
            detail["organization"] = self._related_label(getattr(holder, "subcontractor", None), "name")
        elif obj.holder_kind == "visitor":
            detail["organization"] = getattr(holder, "company", None) or None

        return detail

    def get_device_detail(self, obj):
        device = obj.device
        if device is None:
            return None
        model = device.model
        return {
            "id": device.pk,
            "name": str(model),
            "serial_number": device.serial_number,
            "model": str(model),
            "type": model.type,
            "type_label": model.get_type_display(),
            "status": device.status,
            "status_label": device.get_status_display(),
            "ip_address": device.ip_address,
            "last_heartbeat_at": device.last_heartbeat_at,
        }

    def get_site_detail(self, obj):
        site = obj.site
        return {
            "id": site.pk,
            "name": site.name,
            "code": site.code,
            "type": site.type,
            "type_label": site.get_type_display(),
        }

    def get_zone_detail(self, obj):
        zone = obj.zone
        if zone is None:
            return None
        return {
            "id": zone.pk,
            "name": zone.name,
            "code": zone.code,
            "is_restricted": zone.is_restricted,
        }

    def get_checkpoint_detail(self, obj):
        checkpoint = obj.checkpoint
        if checkpoint is None:
            return None
        return {
            "id": checkpoint.pk,
            "name": checkpoint.name,
            "code": checkpoint.code,
            "type": checkpoint.type,
            "type_label": checkpoint.get_type_display(),
            "mode": checkpoint.mode,
            "mode_label": checkpoint.get_mode_display(),
            "method": checkpoint.method,
            "method_label": checkpoint.get_method_display(),
        }

    def get_operator_detail(self, obj):
        operator = obj.operator
        if operator is None:
            return None
        return {
            "id": operator.pk,
            "name": operator.get_full_name() or operator.email,
            "email": operator.email,
        }

    def get_processing_delay_ms(self, obj):
        if not obj.timestamp or not obj.received_at:
            return None
        return max(0, round((obj.received_at - obj.timestamp).total_seconds() * 1000))

    def _media_url(self, field):
        if not field:
            return None
        try:
            url = field.url
        except (ValueError, AttributeError):
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    @staticmethod
    def _first_value(instance, *attributes):
        for attribute in attributes:
            value = getattr(instance, attribute, None)
            if value:
                return str(value)
        return None

    @staticmethod
    def _person_name(holder):
        first_name = getattr(holder, "first_name", "")
        last_name = getattr(holder, "last_name", "")
        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
        return full_name or str(holder)

    @staticmethod
    def _related_label(instance, attribute):
        if instance is None:
            return None
        return getattr(instance, attribute, None) or str(instance)


class AccessEventDetailSerializer(AccessEventSerializer):
    decision_trace = AccessDecisionSerializer(read_only=True)
    door_commands = DoorCommandSerializer(many=True, read_only=True)


class AccessRuleSerializer(serializers.ModelSerializer):
    class Meta: model = AccessRule; fields = "__all__"


class QRCodeTokenSerializer(serializers.ModelSerializer):
    class Meta: model = QRCodeToken; fields = "__all__"


class ScanSerializer(serializers.Serializer):
    """Payload reçu d'un terminal lors d'un scan."""

    device_serial = serializers.CharField()
    timestamp = serializers.DateTimeField()
    badge_uid = serializers.CharField(required=False, allow_blank=True)
    helmet_uid = serializers.CharField(required=False, allow_blank=True)
    qr_token = serializers.CharField(required=False, allow_blank=True)
    method = serializers.ChoiceField(choices=AccessEvent.METHOD_CHOICES, default="nfc")
    direction = serializers.ChoiceField(choices=AccessEvent.DIRECTION_CHOICES, default="in")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    raw_payload = serializers.JSONField(required=False)
