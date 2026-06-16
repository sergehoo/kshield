"""KAYDAN SHIELD — ModelForms pour le back-office.

Un formulaire par entité principale, conçu pour être consommé par les
vues `CreateView` / `UpdateView` génériques de Django.
"""
from __future__ import annotations

import logging

from django import forms

logger = logging.getLogger(__name__)


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
#: Technologie → liste des types DeviceModel matching.
READER_KIND_TYPES = {
    "uhf": ["reader_uhf_fixed", "reader_uhf_mobile", "portique"],
    "nfc": ["reader_nfc_fixed", "reader_nfc_mobile"],
    "ble": ["beacon_ble"],
    # "zk" — terminaux ZKTeco / Anviz / autres marques à protocole propriétaire.
    # On les colle techniquement en `reader_nfc_*` car ils lisent typiquement
    # des cartes 125 kHz EM ou 13.56 MHz MIFARE, mais le wizard les sépare pour
    # l'UX (configuration spécifique du SDK).
    "zk":  ["reader_nfc_fixed", "reader_nfc_mobile"],
}

READER_KIND_META = {
    "uhf": {
        "label": "Lecteur RFID UHF",
        "icon":  "radio-tower",
        "color": "#F26B1F",
        "hint":  ("Lecteurs longue portée (1 à 10 m) opérant en bande 865-868 MHz (ETSI) "
                  "ou 902-928 MHz (FCC). Typiquement utilisés pour portiques d'accès chantier, "
                  "lecture en mouvement (badges casques)."),
    },
    "nfc": {
        "label": "Lecteur NFC",
        "icon":  "smartphone-nfc",
        "color": "#22d3ee",
        "hint":  ("Lecteurs courte portée (≤ 10 cm) opérant à 13.56 MHz, compatibles "
                  "ISO 14443A/B, MIFARE, FeliCa. Idéaux pour points de pointage employés "
                  "et tourniquets."),
    },
    "ble": {
        "label": "Beacon BLE",
        "icon":  "bluetooth",
        "color": "#a78bfa",
        "hint":  ("Balises Bluetooth Low Energy (2.4 GHz). Diffusent un identifiant "
                  "(iBeacon/Eddystone) capté par l'app mobile pour pointage de proximité "
                  "et géolocalisation indoor."),
    },
    "zk": {
        "label": "Terminal ZKTeco",
        "icon":  "fingerprint",
        "color": "#3b82f6",
        "hint":  ("Terminaux autonomes de pointage / contrôle d'accès (K14, K20, F18, "
                  "MA300, iClock…). Communiquent via le SDK ZKAccess sur le port 4370. "
                  "Gèrent en local la liste des utilisateurs, cartes RFID et empreintes "
                  "digitales, puis poussent les pointages à Shield."),
    },
}


class DeviceForm(StyledModelForm):
    """Form équipement — peut être pré-filtré sur une technologie de lecteur.

    Passer ``reader_kind`` en kwarg (``"uhf"``, ``"nfc"`` ou ``"ble"``) :
    - restreint la liste des `DeviceModel` aux types compatibles ;
    - propose une création inline du DeviceModel si aucun n'existe ;
    - injecte le bon help_text métier sur chaque champ.
    """

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

    def __init__(self, *args, reader_kind: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.reader_kind = (reader_kind or "").lower() if reader_kind else None

        if self.reader_kind and self.reader_kind in READER_KIND_TYPES:
            from devices.models import DeviceModel
            types = READER_KIND_TYPES[self.reader_kind]
            qs = DeviceModel.objects.filter(type__in=types, is_active=True)
            # Pour la techno ZKTeco, filtre EN PLUS par marque pour ne pas
            # mélanger les lecteurs NFC standards avec les terminaux ZK.
            if self.reader_kind == "zk":
                qs = qs.filter(brand__iregex=r"zkteco|anviz|biopointer|zk")
            qs = qs.order_by("brand", "model")
            self.fields["model"].queryset = qs
            self.fields["model"].label = "Modèle d'équipement"
            self.fields["model"].help_text = (
                "Sélectionnez un modèle pré-enregistré, ou "
                "<a href='/device-models/new/' target='_blank' rel='noopener'>"
                "créez-en un</a> si votre matériel n'apparaît pas."
            )

            # Help text contextuels par technologie
            meta = READER_KIND_META[self.reader_kind]
            self.fields["serial_number"].help_text = (
                "Numéro de série imprimé sur le boîtier "
                "(souvent au dos ou dans le menu admin du lecteur)."
            )
            if self.reader_kind == "uhf":
                self.fields["mac_address"].help_text = (
                    "MAC du port Ethernet — pour les lecteurs UHF fixes Impinj/Zebra/CAEN. "
                    "Laisser vide pour les lecteurs UHF mobiles."
                )
                self.fields["ip_address"].help_text = (
                    "IP fixe du lecteur sur le LAN du site (recommandé : DHCP réservé)."
                )
            elif self.reader_kind == "nfc":
                self.fields["ip_address"].help_text = (
                    "IP si le lecteur est mis en réseau (Sycreader/HID). "
                    "Vide si le lecteur est en USB/série."
                )
                self.fields["mac_address"].help_text = (
                    "MAC réseau si applicable. Vide pour USB."
                )
            elif self.reader_kind == "ble":
                self.fields["ip_address"].help_text = (
                    "Non applicable pour un beacon (transmet en broadcast)."
                )
                self.fields["mac_address"].help_text = (
                    "Adresse MAC BLE — 6 octets (ex. AA:BB:CC:DD:EE:FF). "
                    "Sert d'identifiant unique de la balise."
                )
                self.fields["battery_level"].help_text = (
                    "État de la pile bouton CR2477 — critique pour la maintenance."
                )
            elif self.reader_kind == "zk":
                self.fields["ip_address"].help_text = (
                    "IP fixe du terminal sur le LAN — DHCP réservé recommandé. "
                    "Le SDK ZKAccess écoute sur le port 4370 par défaut."
                )
                self.fields["mac_address"].help_text = (
                    "MAC du terminal — visible dans l'admin du device (Menu → Système → Info)."
                )
                self.fields["serial_number"].help_text = (
                    "Numéro de série imprimé au dos du terminal "
                    "(ex. <code>CQUJ222460289</code>). Auto-détecté après "
                    "premier dialogue SDK."
                )
                self.fields["firmware_version"].help_text = (
                    "Sera auto-détecté lors du premier dialogue ZKAccess "
                    "(<code>Ver 6.60 Sep 19 2019</code>)."
                )

        # Si un seul DeviceModel matche, on le présélectionne pour gagner un clic
        if self.reader_kind and len(self.fields["model"].queryset) == 1:
            self.fields["model"].initial = self.fields["model"].queryset.first()


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


class CameraForm(StyledModelForm):
    """Formulaire complet pour ajouter/configurer une caméra IP.

    Le champ ``password`` est masqué par défaut. Si on est en mode édition,
    on ne le re-pré-remplit pas (sécurité) — laisser vide pour conserver
    l'ancien, ou saisir une nouvelle valeur pour mettre à jour.
    """

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password",
                                            "placeholder": "(inchangé)"}),
        help_text="Laisser vide pour conserver le mot de passe actuel.",
    )

    class Meta:
        from devices.models import Camera
        model = Camera
        fields = [
            # Identité
            "name", "site", "zone", "location_label",
            # Connexion
            "rtsp_url", "transport", "codec",
            "username", "password",
            # Re-stream
            "target_width", "target_height", "target_fps", "jpeg_quality",
            # ONVIF
            "onvif_enabled", "onvif_host", "onvif_port",
            # Pipeline IA
            "enable_face_recognition", "enable_motion_detection", "enable_recording",
            # Statut
            "is_active",
        ]
        widgets = {
            "rtsp_url": forms.TextInput(attrs={
                "placeholder": "rtsp://user:pass@192.168.1.50:554/Streaming/Channels/101",
            }),
            "location_label": forms.TextInput(attrs={
                "placeholder": "Mât SE, hauteur 4m",
            }),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Si password vide en édition → conserve l'ancien
        pwd = self.cleaned_data.get("password", "")
        if not pwd and instance.pk:
            try:
                from devices.models import Camera as _Cam
                instance.password = _Cam.objects.only("password").get(pk=instance.pk).password
            except Exception:
                pass
        elif pwd:
            instance.password = pwd
        if commit:
            instance.save()
            self.save_m2m()
        return instance


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
            logger.warning("Affectation tenant KAYDAN sur User échouée", exc_info=True)
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
    """Création / édition d'un rôle avec cases à cocher par catégorie.

    Le champ `permissions_codes` est une MultipleChoiceField alimentée par
    `accounts.rbac.PERMISSION_CATALOG`. Les permissions custom (codes hors
    catalogue) restent visibles dans `permissions_text` (textarea avancée).
    """

    permissions_codes = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple,
        label="Permissions accordées",
    )
    permissions_text = forms.CharField(
        required=False, label="Permissions custom (avancé — un code par ligne)",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder":
            "Ex: integrations.export_hris\ncustom.tool"}),
        help_text="Optionnel : codes non-listés dans le catalogue ci-dessus.",
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
        from accounts.rbac import PERMISSION_CATALOG, all_known_codes

        choices = []
        for category, items in PERMISSION_CATALOG:
            for code, label in items:
                choices.append((code, f"{label} · {code}"))
        self.fields["permissions_codes"].choices = choices
        # On expose aussi les catégories au template via attribut helper
        self.permissions_catalog = PERMISSION_CATALOG

        if self.instance and self.instance.pk:
            existing = set(self.instance.permissions.values_list("code", flat=True))
            known = set(all_known_codes())
            self.fields["permissions_codes"].initial = sorted(existing & known)
            custom = sorted(existing - known)
            if custom:
                self.fields["permissions_text"].initial = "\n".join(custom)
        _apply_widget_classes(self)

    def save(self, commit=True):
        role = super().save(commit=commit)
        if commit:
            self._sync_permissions(role)
            # invalide le cache RBAC pour tous les users assignés à ce rôle
            try:
                from accounts.rbac import invalidate_user_perms
                for uid in role.assignments.values_list("user_id", flat=True).distinct():
                    invalidate_user_perms(uid)
            except Exception:
                logger.warning("Invalidation cache RBAC après update rôle %s échouée",
                                getattr(role, "code", "?"), exc_info=True)
        return role

    def _sync_permissions(self, role):
        from accounts.models import RolePermission
        codes = set(self.cleaned_data.get("permissions_codes") or [])
        raw = self.cleaned_data.get("permissions_text") or ""
        codes |= {ln.strip() for ln in raw.splitlines() if ln.strip()}
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


# ===========================================================================
# Workflow visiteurs (P0)
# ===========================================================================
class VisitPurposeForm(StyledModelForm):
    class Meta:
        from visitors.models import VisitPurpose
        model = VisitPurpose
        fields = ["code", "label", "requires_approval", "is_active"]


class VisitorPassForm(StyledModelForm):
    class Meta:
        from visitors.models import VisitorPass
        model = VisitorPass
        fields = ["visit_request", "type", "valid_from", "valid_until"]
        widgets = {
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class WatchlistForm(StyledModelForm):
    class Meta:
        from visitors.models import Watchlist
        model = Watchlist
        fields = ["visitor", "full_name", "id_number", "site",
                   "reason", "is_active", "expires_at"]
        widgets = {
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "reason": forms.Textarea(attrs={"rows": 3}),
        }


class VisitorInvitationForm(StyledModelForm):
    class Meta:
        from visitors.models import VisitorInvitation
        model = VisitorInvitation
        fields = ["visit_request", "sent_to_email", "sent_to_phone", "expires_at"]
        widgets = {
            "expires_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


# ===========================================================================
# FraudInvestigation (P0 #2)
# ===========================================================================
class FraudInvestigationForm(StyledModelForm):
    class Meta:
        from antifraud.models import FraudInvestigation
        model = FraudInvestigation
        exclude = ("tenant", "created_by", "updated_by")
        widgets = {
            "started_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "closed_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


# ===========================================================================
# Dashboards configurables (P3)
# ===========================================================================
class DashboardForm(StyledModelForm):
    class Meta:
        from reports.models import Dashboard
        model = Dashboard
        fields = ["name", "code", "layout", "is_default"]
        widgets = {
            "layout": forms.Textarea(attrs={"rows": 3,
                "placeholder": '{"columns": 3, "row_height": 200}'}),
        }


class DashboardWidgetForm(StyledModelForm):
    class Meta:
        from reports.models import DashboardWidget
        model = DashboardWidget
        fields = ["dashboard", "kind", "title", "query", "options", "position"]
        widgets = {
            "query": forms.Textarea(attrs={"rows": 4,
                "placeholder": '{"select": "count(*)", "from": "access_event", "where": {"decision":"granted"}}'}),
            "options": forms.Textarea(attrs={"rows": 3,
                "placeholder": '{"color": "orange", "icon": "bar-chart-3"}'}),
            "position": forms.Textarea(attrs={"rows": 2,
                "placeholder": '{"x": 0, "y": 0, "w": 1, "h": 1}'}),
        }


# ===========================================================================
# Devices monitoring (P1 #4) — Maintenance, Firmware, OTA
# ===========================================================================
class DeviceMaintenanceForm(StyledModelForm):
    class Meta:
        from devices.models import DeviceMaintenance
        model = DeviceMaintenance
        fields = ["device", "kind", "technician_name", "started_at",
                   "ended_at", "description", "cost"]
        widgets = {
            "started_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ended_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class FirmwareVersionForm(StyledModelForm):
    class Meta:
        from devices.models import FirmwareVersion
        model = FirmwareVersion
        fields = ["device_model", "version", "release_notes", "file", "is_published"]
        widgets = {
            "release_notes": forms.Textarea(attrs={"rows": 3}),
        }


class OTAUpdateForm(StyledModelForm):
    class Meta:
        from devices.models import OTAUpdate
        model = OTAUpdate
        fields = ["device", "firmware", "status", "scheduled_for"]
        widgets = {
            "scheduled_for": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


# ===========================================================================
# Pointage RH (P1 #2) — Corrections, Overtime, Roster
# ===========================================================================
class AttendanceCorrectionForm(StyledModelForm):
    class Meta:
        from attendance.models import AttendanceCorrection
        model = AttendanceCorrection
        fields = ["attendance_day", "field_name", "previous_value",
                   "new_value", "reason", "performed_by"]
        widgets = {
            "reason": forms.Textarea(attrs={"rows": 3}),
        }


class RosterForm(StyledModelForm):
    class Meta:
        from attendance.models import Roster
        model = Roster
        fields = ["site", "holder_kind", "holder_object_id", "date",
                   "expected_start", "expected_end", "is_present_expected"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "expected_start": forms.TimeInput(attrs={"type": "time"}),
            "expected_end": forms.TimeInput(attrs={"type": "time"}),
        }


class OvertimeCalculationForm(StyledModelForm):
    class Meta:
        from attendance.models import OvertimeCalculation
        model = OvertimeCalculation
        fields = ["employee", "worker", "week_start", "base_minutes",
                   "overtime_125_minutes", "overtime_150_minutes",
                   "night_minutes"]
        widgets = {
            "week_start": forms.DateInput(attrs={"type": "date"}),
        }


# ===========================================================================
# Workers — Certifications, Crews, Assignments (P1 #1)
# ===========================================================================
class WorkerCertificationForm(StyledModelForm):
    class Meta:
        from ouvriers.models import WorkerCertification
        model = WorkerCertification
        fields = ["worker", "code", "label", "issued_at",
                   "valid_until", "document", "notes"]
        widgets = {
            "issued_at": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class CrewForm(StyledModelForm):
    class Meta:
        from ouvriers.models import Crew
        model = Crew
        fields = ["site", "name", "foreman", "is_active"]


class WorkerAssignmentForm(StyledModelForm):
    class Meta:
        from ouvriers.models import WorkerAssignment
        model = WorkerAssignment
        fields = ["worker", "site", "crew", "started_at",
                   "ended_at", "is_active", "notes"]
        widgets = {
            "started_at": forms.DateInput(attrs={"type": "date"}),
            "ended_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


# ===========================================================================
# AccessRule (P0 #3)
# ===========================================================================
class AccessRuleForm(StyledModelForm):
    class Meta:
        from access_control.models import AccessRule
        model = AccessRule
        fields = ["site", "code", "name", "type", "severity",
                   "is_active", "conditions", "actions", "description"]
        widgets = {
            "conditions": forms.Textarea(attrs={"rows": 5,
                "placeholder": '{"start_time": "06:00", "end_time": "20:00", "days": [1,2,3,4,5]}'}),
            "actions": forms.Textarea(attrs={"rows": 3,
                "placeholder": '{"on_violation": "deny"}'}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }
