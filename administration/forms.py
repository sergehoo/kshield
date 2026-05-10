"""KAYDAN SHIELD — ModelForms pour le back-office.

Un formulaire par entité principale, conçu pour être consommé par les
vues `CreateView` / `UpdateView` génériques de Django.
"""
from __future__ import annotations

from django import forms


# ---------------------------------------------------------------------------
# Widget defaults
# ---------------------------------------------------------------------------
def _apply_widget_classes(form):
    """Style chaque champ d'un form pour matcher le design KAYDAN SHIELD."""
    for name, field in form.fields.items():
        widget = field.widget
        css = widget.attrs.get("class", "")
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs["class"] = (css + " form-select").strip()
        elif isinstance(widget, forms.Textarea):
            widget.attrs["class"] = (css + " form-textarea").strip()
        elif isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
            pass
        elif isinstance(widget, forms.ClearableFileInput):
            widget.attrs["class"] = (css + " form-input").strip()
        else:
            widget.attrs["class"] = (css + " form-input").strip()
        if isinstance(widget, (forms.TextInput, forms.EmailInput, forms.URLInput, forms.NumberInput)):
            widget.attrs.setdefault("placeholder", field.label or name)


class StyledModelForm(forms.ModelForm):
    """Mixin commun : applique les classes CSS automatiquement."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_widget_classes(self)


# ===========================================================================
# Identités — Employees, Workers, Visitors
# ===========================================================================
class EmployeeForm(StyledModelForm):
    class Meta:
        from employees.models import Employee
        model = Employee
        fields = [
            "matricule", "first_name", "last_name", "email", "phone",
            "photo", "id_document", "company", "department", "position",
            "manager", "contract_type", "status", "work_location",
            "hired_at", "ended_at",
        ]
        widgets = {
            "hired_at": forms.DateInput(attrs={"type": "date"}),
            "ended_at": forms.DateInput(attrs={"type": "date"}),
        }


class WorkerForm(StyledModelForm):
    class Meta:
        from ouvriers.models import Worker
        model = Worker
        fields = [
            "matricule", "first_name", "last_name", "date_of_birth", "phone",
            "photo", "id_document_number", "id_document_file",
            "trade", "subcontractor", "helmet_size", "status",
            "emergency_contact_name", "emergency_contact_phone",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }


class SubcontractorForm(StyledModelForm):
    class Meta:
        from ouvriers.models import Subcontractor
        model = Subcontractor
        fields = [
            "name", "code", "legal_name", "tax_id",
            "contact_name", "contact_phone", "contact_email",
            "contract_start", "contract_end", "is_active",
        ]
        widgets = {
            "contract_start": forms.DateInput(attrs={"type": "date"}),
            "contract_end": forms.DateInput(attrs={"type": "date"}),
        }


class VisitorForm(StyledModelForm):
    class Meta:
        from visitors.models import Visitor
        model = Visitor
        exclude = ("tenant", "created_by", "updated_by",
                   "pseudonymized_at", "uuid")


class VisitRequestForm(StyledModelForm):
    class Meta:
        from visitors.models import VisitRequest
        model = VisitRequest
        fields = [
            "visitor", "site", "host_employee", "purpose", "purpose_other",
            "mode", "status", "scheduled_at", "expected_duration_minutes",
            "notes",
        ]
        widgets = {
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


# ===========================================================================
# Sites & Zones
# ===========================================================================
class SiteForm(StyledModelForm):
    class Meta:
        from sites.models import Site
        model = Site
        fields = [
            "name", "code", "type", "status", "company",
            "latitude", "longitude", "geofence", "timezone",
            "project_manager_name", "site_supervisor_name", "risk_level",
            "start_date", "end_date",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "geofence": forms.Textarea(attrs={"rows": 3, "placeholder": '{}'}),
        }


class ZoneForm(StyledModelForm):
    class Meta:
        from sites.models import Zone
        model = Zone
        fields = ["site", "parent", "name", "code", "description", "is_restricted"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


# ===========================================================================
# Devices, Badges, Helmets
# ===========================================================================
class DeviceForm(StyledModelForm):
    class Meta:
        from devices.models import Device
        model = Device
        fields = [
            "model", "serial_number", "site", "zone", "checkpoint",
            "status", "ip_address", "mac_address", "firmware_version",
            "battery_level", "commissioned_at",
        ]
        widgets = {
            "commissioned_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class DeviceModelForm(StyledModelForm):
    class Meta:
        from devices.models import DeviceModel
        model = DeviceModel
        fields = ["brand", "model", "type", "spec", "is_active"]
        widgets = {
            "spec": forms.Textarea(attrs={"rows": 3, "placeholder": '{}'}),
        }


class BadgeForm(StyledModelForm):
    class Meta:
        from devices.models import Badge
        model = Badge
        fields = [
            "uid", "type", "category", "status",
            "holder_kind", "holder_object_id",
            "paired_helmet", "qr_payload",
            "valid_from", "valid_until", "expires_at",
        ]
        widgets = {
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
        }


class HelmetForm(StyledModelForm):
    class Meta:
        from devices.models import Helmet
        model = Helmet
        fields = [
            "serial_number", "uhf_tag_uid", "ble_beacon_uid",
            "status", "size", "current_worker", "commissioned_at",
        ]
        widgets = {
            "commissioned_at": forms.DateInput(attrs={"type": "date"}),
        }


# ===========================================================================
# Gateway, Antifraud, Notifications
# ===========================================================================
class SiteGatewayForm(StyledModelForm):
    class Meta:
        from core.models import SiteGateway
        model = SiteGateway
        fields = [
            "site", "name", "code", "hardware", "status",
            "lan_ip", "public_ip", "vpn_endpoint", "api_port",
            "serial_number", "mac_address", "os_version", "kshield_version",
            "is_active", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class FraudRuleForm(StyledModelForm):
    class Meta:
        from antifraud.models import FraudRule
        model = FraudRule
        exclude = ("tenant", "created_by", "updated_by")


class NotificationTemplateForm(StyledModelForm):
    class Meta:
        from notifications.models import NotificationTemplate
        model = NotificationTemplate
        exclude = ("tenant", "created_by", "updated_by")


# ===========================================================================
# Système : Tenant, Company, FeatureFlag
# ===========================================================================
class TenantForm(StyledModelForm):
    class Meta:
        from core.models import Tenant
        model = Tenant
        fields = ["name", "code", "logo", "timezone", "currency", "is_active", "settings"]
        widgets = {
            "settings": forms.Textarea(attrs={"rows": 3, "placeholder": '{}'}),
        }


class CompanyForm(StyledModelForm):
    class Meta:
        from core.models import Company
        model = Company
        fields = [
            "name", "code", "legal_name", "tax_id", "sector",
            "contact_name", "contact_email", "contact_phone",
            "logo", "is_active",
        ]
        widgets = {
            "logo": forms.ClearableFileInput(attrs={
                "accept": "image/png, image/jpeg, image/svg+xml",
            }),
        }


class FeatureFlagForm(StyledModelForm):
    class Meta:
        from core.models import FeatureFlag
        model = FeatureFlag
        fields = ["code", "is_enabled", "description", "payload"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "payload": forms.Textarea(attrs={"rows": 3, "placeholder": '{}'}),
        }


# ===========================================================================
# Utilisateurs / Rôles / API keys
# ===========================================================================
class UserCreateForm(forms.ModelForm):
    """Formulaire de création d'utilisateur back-office."""

    password = forms.CharField(
        label="Mot de passe", min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="8 caractères minimum.",
    )
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=None, required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Rôles attribués",
        help_text="Sélectionnez les rôles métiers qui définissent les permissions.",
    )

    class Meta:
        from accounts.models import User
        model = User
        fields = [
            "email", "first_name", "last_name", "phone",
            "company", "is_active", "is_staff", "mfa_enabled", "photo",
        ]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import Role
        self.fields["roles"].queryset = Role.objects.order_by("name")
        _apply_widget_classes(self)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Les deux mots de passe ne correspondent pas.")
        email = (cleaned.get("email") or "").strip().lower()
        if email:
            from accounts.models import User
            if User.objects.filter(email__iexact=email).exists():
                self.add_error("email", "Un compte existe déjà avec cet email.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        try:
            from core.services import get_kaydan_tenant
            user.tenant = get_kaydan_tenant()
        except Exception:
            pass
        if commit:
            user.save()
            self._save_roles(user)
        return user

    def _save_roles(self, user):
        from accounts.models import RoleAssignment
        roles = self.cleaned_data.get("roles") or []
        RoleAssignment.objects.filter(user=user).delete()
        for r in roles:
            RoleAssignment.objects.get_or_create(user=user, role=r, site=None)


class UserUpdateForm(forms.ModelForm):
    """Édition d'un utilisateur (sans modification du mot de passe)."""

    roles = forms.ModelMultipleChoiceField(
        queryset=None, required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Rôles attribués",
    )

    class Meta:
        from accounts.models import User
        model = User
        fields = [
            "email", "first_name", "last_name", "phone",
            "company", "is_active", "is_staff", "mfa_enabled", "photo",
        ]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import Role
        self.fields["roles"].queryset = Role.objects.order_by("name")
        if self.instance and self.instance.pk:
            self.fields["roles"].initial = list(
                self.instance.role_assignments.values_list("role_id", flat=True)
            )
        _apply_widget_classes(self)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            UserCreateForm._save_roles(self, user)
        return user


class UserPasswordForm(forms.Form):
    """Réinitialisation / changement du mot de passe d'un utilisateur."""

    password = forms.CharField(
        label="Nouveau mot de passe", min_length=8,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    force_change_at_next_login = forms.BooleanField(
        required=False,
        label="Forcer le changement à la prochaine connexion",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_widget_classes(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "Les deux mots de passe ne correspondent pas.")
        return cleaned


class RoleForm(StyledModelForm):
    """Création / édition d'un rôle."""

    permissions_text = forms.CharField(
        required=False, label="Permissions (codes, un par ligne)",
        widget=forms.Textarea(attrs={"rows": 6, "placeholder":
            "Ex:\nantifraud.acknowledge_alert\nbadges.issue_worker\nemployees.view"}),
        help_text="Une permission par ligne (format module.action).",
    )

    class Meta:
        from accounts.models import Role
        model = Role
        fields = ["code", "name", "scope", "description", "is_system"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["permissions_text"].initial = "\n".join(
                self.instance.permissions.values_list("code", flat=True).order_by("code")
            )
        _apply_widget_classes(self)

    def save(self, commit=True):
        role = super().save(commit=commit)
        if commit:
            self._sync_permissions(role)
        return role

    def _sync_permissions(self, role):
        from accounts.models import RolePermission
        raw = self.cleaned_data.get("permissions_text") or ""
        codes = {ln.strip() for ln in raw.splitlines() if ln.strip()}
        existing = set(role.permissions.values_list("code", flat=True))
        for c in codes - existing:
            RolePermission.objects.get_or_create(role=role, code=c)
        if existing - codes:
            RolePermission.objects.filter(role=role, code__in=existing - codes).delete()


class APIKeyForm(StyledModelForm):
    class Meta:
        from accounts.models import APIKey
        model = APIKey
        fields = ["name", "scope", "site", "is_active", "expires_at"]
        widgets = {
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


# ===========================================================================
# Pointage / présence
# ===========================================================================
class LeaveRequestForm(StyledModelForm):
    class Meta:
        from attendance.models import LeaveRequest
        model = LeaveRequest
        fields = [
            "employee", "worker", "type", "status",
            "start_date", "end_date", "reason", "document",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 3}),
        }


class OvertimeRuleForm(StyledModelForm):
    class Meta:
        from attendance.models import OvertimeRule
        model = OvertimeRule
        fields = [
            "company", "name", "weekly_threshold_hours",
            "rate_125", "rate_150", "night_rate", "is_active",
        ]


# ===========================================================================
# Audit / conformité
# ===========================================================================
class LegalRetentionPolicyForm(StyledModelForm):
    class Meta:
        from audit.models import LegalRetentionPolicy
        model = LegalRetentionPolicy
        fields = ["target_model", "retention_days", "legal_basis", "is_active"]
        widgets = {
            "legal_basis": forms.Textarea(attrs={"rows": 3}),
        }


class DataExportRequestForm(StyledModelForm):
    class Meta:
        from audit.models import DataExportRequest
        model = DataExportRequest
        fields = [
            "subject_holder_kind", "subject_holder_id", "kind",
            "status", "parameters", "expires_at",
        ]
        widgets = {
            "parameters": forms.Textarea(attrs={"rows": 4,
                "placeholder": '{"include_audit": true}'}),
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class ConformityRegisterForm(StyledModelForm):
    class Meta:
        from audit.models import ConformityRegister
        model = ConformityRegister
        fields = [
            "site", "kind", "title", "performed_at",
            "performed_by", "result", "document",
        ]
        widgets = {
            "performed_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "result": forms.Textarea(attrs={"rows": 3}),
        }


# ===========================================================================
# Reporting
# ===========================================================================
class ReportForm(StyledModelForm):
    class Meta:
        from reports.models import Report
        model = Report
        fields = [
            "name", "code", "type", "description",
            "query", "scope", "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "query": forms.Textarea(attrs={"rows": 6,
                "placeholder": '{"select": ["…"], "from": "access_event"}'}),
        }


class ReportScheduleForm(StyledModelForm):
    class Meta:
        from reports.models import ReportSchedule
        model = ReportSchedule
        fields = ["report", "frequency", "cron_expression",
                  "parameters", "is_active"]
        widgets = {
            "parameters": forms.Textarea(attrs={"rows": 3}),
        }


# ===========================================================================
# Mobile / sync
# ===========================================================================
class MobileDeviceForm(StyledModelForm):
    class Meta:
        from mobile_sync.models import MobileDevice
        model = MobileDevice
        fields = [
            "user", "device_id", "name", "os", "os_version",
            "app_version", "site", "api_key", "status",
        ]


# ===========================================================================
# AI assistant
# ===========================================================================
class AIPromptTemplateForm(StyledModelForm):
    class Meta:
        from ai_assistant.models import AIPromptTemplate
        model = AIPromptTemplate
        fields = ["code", "role", "name", "system_prompt", "is_active"]
        widgets = {
            "system_prompt": forms.Textarea(attrs={"rows": 8,
                "placeholder": "Tu es l'assistant KAYDAN SHIELD…"}),
        }
