"""KAYDAN SHIELD — Vues CRUD génériques pour le back-office.

Pattern : pour chaque entité, on définit une `EntityCRUD` qui regroupe
list / detail / create / update / delete avec un layout unifié.

`make_crud()` prend un dict de config et retourne 4 classes
(Create / Detail / Update / Delete) prêtes à câbler dans `urls.py`.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from . import forms as kforms

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mixin injection tenant — KAYDAN est l'unique tenant du projet.
# ---------------------------------------------------------------------------
class InjectKaydanTenantMixin:
    """Auto-affecte le tenant KAYDAN avant sauvegarde si le modèle l'exige."""

    def form_valid(self, form):
        instance = form.instance
        if hasattr(instance, "tenant_id") and not getattr(instance, "tenant_id", None):
            try:
                from core.services import get_kaydan_tenant
                instance.tenant = get_kaydan_tenant()
            except Exception:
                logger.warning("Auto-affectation tenant KAYDAN échouée pour %s",
                               type(instance).__name__, exc_info=True)
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Mixin commun
# ---------------------------------------------------------------------------
class AdminContextMixin:
    """Pose les variables consommées par templates/layout/base.html.

    Force aussi l'authentification — toutes les vues CRUD du back-office
    nécessitent un user connecté.
    """

    active_nav: str = ""
    page_title: str = ""
    breadcrumb: str = ""
    list_url_name: str = ""
    entity_label: str = "Élément"
    entity_label_plural: str = "Éléments"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from urllib.parse import urlencode
            from django.shortcuts import redirect
            return redirect(f"/auth/login/?{urlencode({'next': request.get_full_path()})}")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "active_nav": self.active_nav,
            "page_title": self.page_title,
            "breadcrumb": self.breadcrumb or self.page_title,
            "list_url_name": self.list_url_name,
            "entity_label": self.entity_label,
            "entity_label_plural": self.entity_label_plural,
            "open_alerts_count": self._safe_count("antifraud", "FraudAlert", status="open"),
        })
        try:
            from accounts.rbac import user_permissions
            ctx["user_perms"] = user_permissions(self.request.user)
        except Exception:
            ctx["user_perms"] = set()
        return ctx

    @staticmethod
    def _safe_count(app_label, model_name, **filters):
        try:
            from django.apps import apps
            return apps.get_model(app_label, model_name).objects.filter(**filters).count()
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Factory CRUD
# ---------------------------------------------------------------------------
# ─── Module-level constants pour _build_fields() ─────────────────────
# (sortis de make_crud() pour qu'ils soient résolvables depuis les méthodes
#  de classe inner — sinon Python lève NameError sur le scope de classe.)

_HIDDEN_FIELDS = {
    "id", "uuid", "tenant", "created_by", "updated_by",
    "secret_hash", "password", "deleted_by",
}

_CATEGORY_BY_FIELD = {
    "first_name": "identity", "last_name": "identity",
    "name": "identity", "title": "identity", "full_name": "identity",
    "matricule": "identity", "code": "identity",
    "serial_number": "identity", "uid": "identity",
    "license_plate": "identity",
    "id_number": "identity", "id_type": "identity",
    "nationality": "identity", "date_of_birth": "identity",
    "email": "contact", "phone": "contact", "address": "contact",
    "contact_email": "contact", "contact_phone": "contact",
    "contact_name": "contact",
    "emergency_contact_name": "contact", "emergency_contact_phone": "contact",
    "company": "links", "department": "links", "position": "links",
    "manager": "links", "subcontractor": "links", "trade": "links",
    "site": "links", "zone": "links", "checkpoint": "links",
    "model": "links", "host_employee": "links",
    "current_worker": "links", "paired_helmet": "links",
    "rule": "links", "report": "links", "device": "links",
    "user": "links", "recipient": "links", "template": "links",
    "purpose": "links", "visit_request": "links",
    "approved_by": "links",
    "status": "status", "is_active": "status",
    "contract_type": "status", "work_location": "status",
    "severity": "status", "scope": "status", "type": "status",
    "kind": "status", "category": "status", "method": "status",
    "decision": "status", "direction": "status",
    "hired_at": "status", "ended_at": "status",
    "created_at": "status", "updated_at": "status",
    "issued_at": "status", "expires_at": "status",
    "valid_from": "status", "valid_until": "status",
    "scheduled_at": "status", "raised_at": "status",
    "description": "notes", "notes": "notes", "reason": "notes",
    "denial_reason": "notes", "purpose_other": "notes",
    "result": "notes", "legal_basis": "notes",
}

_ICON_BY_FIELD = {
    "first_name": "user", "last_name": "user", "name": "type",
    "title": "type", "matricule": "hash", "code": "hash",
    "serial_number": "barcode", "uid": "fingerprint",
    "id_number": "scan-line", "id_type": "id-card",
    "email": "mail", "phone": "phone", "address": "map-pin",
    "contact_email": "mail", "contact_phone": "phone",
    "contact_name": "user-round",
    "emergency_contact_name": "siren",
    "emergency_contact_phone": "siren",
    "company": "building-2", "department": "users",
    "position": "briefcase", "manager": "user-cog",
    "subcontractor": "users-round", "trade": "wrench",
    "site": "map-pin", "zone": "shapes", "checkpoint": "scan-line",
    "model": "cpu", "host_employee": "user-check",
    "current_worker": "hard-hat", "paired_helmet": "hard-hat",
    "rule": "shield-alert", "device": "cpu",
    "user": "user", "recipient": "send",
    "template": "layout-template", "purpose": "target",
    "approved_by": "user-check",
    "status": "activity", "is_active": "toggle-right",
    "contract_type": "file-signature",
    "work_location": "map-pinned",
    "severity": "alert-triangle", "scope": "globe",
    "type": "tag", "kind": "tag", "category": "tag",
    "method": "scan", "decision": "gavel", "direction": "log-in",
    "hired_at": "calendar-plus", "ended_at": "calendar-x",
    "created_at": "clock", "updated_at": "refresh-cw",
    "issued_at": "calendar-check", "expires_at": "calendar-clock",
    "valid_from": "calendar-arrow-up", "valid_until": "calendar-arrow-down",
    "scheduled_at": "calendar", "raised_at": "alarm-clock",
    "description": "file-text", "notes": "sticky-note",
    "reason": "message-square", "denial_reason": "ban",
    "purpose_other": "info", "result": "check-square",
    "legal_basis": "scale", "nationality": "flag",
    "date_of_birth": "cake", "photo": "image",
    "id_document": "file-image", "logo": "image",
    "latitude": "map", "longitude": "map",
    "geofence": "shapes", "polygon": "shapes",
    "weekly_threshold_hours": "timer",
    "rate_125": "percent", "rate_150": "percent",
    "night_rate": "moon",
    "retention_days": "archive",
    "uhf_tag_uid": "radio-tower", "ble_beacon_uid": "bluetooth",
}

_CATEGORY_META = (
    ("identity", "Identité", "id-card"),
    ("contact", "Contact", "phone"),
    ("links", "Liens", "link-2"),
    ("status", "Statut & dates", "activity"),
    ("notes", "Notes & description", "file-text"),
    ("other", "Autres informations", "info"),
)


def make_crud(
    *,
    model,
    form_class,
    active_nav: str,
    list_url_name: str,
    url_prefix: str,
    entity_label: str,
    entity_label_plural: str,
    url_key: Optional[str] = None,
    detail_template: Optional[str] = None,
    form_template: str = "administration/_form.html",
    delete_template: str = "administration/_confirm_delete.html",
    detail_context_extras=None,
):
    """Construit 4 classes (Create, Detail, Update, Delete) pour une entité."""

    success_url = reverse_lazy(list_url_name)
    _form_cls = form_class
    _model = model
    _active = active_nav
    _list_name = list_url_name
    _url_key = url_key or active_nav

    class _Create(AdminContextMixin, InjectKaydanTenantMixin, SuccessMessageMixin, CreateView):
        form_class = _form_cls
        success_message = f"{entity_label} créé avec succès."
        template_name = form_template
        success_url = reverse_lazy(list_url_name)
        page_title = f"Nouveau {entity_label.lower()}"

        def get_form_class(self): return _form_cls

        def get(self, request, *args, **kwargs):
            import time
            import logging
            log = logging.getLogger("admin.crud")
            t0 = time.perf_counter()
            resp = super().get(request, *args, **kwargs)
            elapsed = int((time.perf_counter() - t0) * 1000)
            if elapsed > 500:
                log.warning(
                    "SLOW admin CRUD Create GET %s: %dms (path=%s)",
                    _url_key, elapsed, request.path,
                )
            return resp

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            ctx["url_key"] = _url_key
            return ctx

    class _Detail(AdminContextMixin, DetailView):
        template_name = detail_template or "administration/_detail.html"

        def get_queryset(self):
            # Pre-load systématique des FK usuels pour éviter les N+1 dans
            # _build_fields (qui accède à chaque relation via getattr).
            qs = super().get_queryset()
            related = []
            for f in self.model._meta.get_fields():
                if (
                    getattr(f, "is_relation", False)
                    and getattr(f, "many_to_one", False)
                    and getattr(f, "concrete", False)
                ):
                    related.append(f.name)
            if related:
                qs = qs.select_related(*related[:20])   # cap à 20 pour éviter les jointures monstres
            return qs

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            ctx["page_title"] = f"{entity_label} · {self.object}"
            ctx["fields"] = self._build_fields()
            ctx["update_url"] = reverse(f"admin-{_url_key}-update", args=[self.object.pk])
            ctx["delete_url"] = reverse(f"admin-{_url_key}-delete", args=[self.object.pk])
            ctx["url_key"] = _url_key
            if detail_context_extras is not None:
                try:
                    extras = detail_context_extras(self, ctx) or {}
                    ctx.update(extras)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "detail_context_extras failed for %s", _url_key,
                    )
            return ctx

        def _build_fields(self):
            """Retourne un dict {category_key: [{label, value, icon, raw}, ...]}.

            Le dict respecte l'ordre de _CATEGORY_META. Les méta-champs internes
            (uuid, tenant, etc.) sont exclus.
            """
            from collections import OrderedDict
            grouped = OrderedDict()
            for key, _, _ in _CATEGORY_META:
                grouped[key] = []

            for f in self.object._meta.get_fields():
                fname = getattr(f, "name", None)
                if not fname or fname in _HIDDEN_FIELDS:
                    continue
                if f.is_relation and f.many_to_many:
                    try:
                        vals = list(getattr(self.object, fname).all()[:5])
                        val = ", ".join(str(v) for v in vals) if vals else None
                    except Exception:
                        val = None
                elif f.is_relation and f.one_to_many:
                    continue  # reverse relations affichées via context_extras
                elif f.is_relation:
                    try: val = getattr(self.object, fname, None)
                    except Exception: val = None
                else:
                    val = getattr(self.object, fname, None)

                # Préfère display() pour les choices fields (status, type, etc.)
                getter = f"get_{fname}_display"
                if hasattr(self.object, getter):
                    try:
                        val = getattr(self.object, getter)()
                    except Exception:
                        logger.debug("display getter %s a levé pour %s", getter,
                                      type(self.object).__name__, exc_info=True)

                if hasattr(f, "verbose_name"):
                    label = str(f.verbose_name).capitalize()
                else:
                    label = fname.replace("_", " ").capitalize()

                category = _CATEGORY_BY_FIELD.get(fname, "other")
                icon = _ICON_BY_FIELD.get(fname, "circle-dot")

                grouped[category].append({
                    "label": label, "value": val, "icon": icon,
                    "raw_name": fname,
                })

            # Liste des sections non-vides + meta
            sections = []
            for key, title, sec_icon in _CATEGORY_META:
                items = grouped.get(key) or []
                if items:
                    sections.append({"key": key, "title": title,
                                      "icon": sec_icon, "items": items})
            return sections

    class _Update(AdminContextMixin, InjectKaydanTenantMixin, SuccessMessageMixin, UpdateView):
        form_class = _form_cls
        success_message = f"{entity_label} mis à jour."
        template_name = form_template
        success_url = reverse_lazy(list_url_name)

        def get_form_class(self): return _form_cls

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            ctx["page_title"] = f"Modifier · {self.object}"
            ctx["url_key"] = _url_key
            return ctx

    class _Delete(AdminContextMixin, DeleteView):
        template_name = delete_template
        success_url = reverse_lazy(list_url_name)

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            ctx["page_title"] = f"Supprimer · {self.object}"
            ctx["url_key"] = _url_key
            return ctx

        def form_valid(self, form):
            messages.success(self.request, f"{entity_label} supprimé.")
            return super().form_valid(form)

    for cls in (_Create, _Detail, _Update, _Delete):
        cls.model = model
        cls.active_nav = active_nav
        cls.list_url_name = list_url_name
        cls.entity_label = entity_label
        cls.entity_label_plural = entity_label_plural

    class CRUD:
        Create = _Create
        Detail = _Detail
        Update = _Update
        Delete = _Delete

    return CRUD


# ---------------------------------------------------------------------------
# Context extras spécifiques par entité
# ---------------------------------------------------------------------------
def _device_detail_extras(view, ctx):
    """Injecte is_zkteco_device pour afficher les boutons ZK conditionnellement."""
    try:
        from devices.zk_client import is_zkteco_device
        return {"is_zkteco_device": is_zkteco_device(view.object)}
    except Exception:
        return {"is_zkteco_device": False}


def _badge_detail_extras(view, ctx):
    """Injecte timeline (assignments + scans) pour le badge detail."""
    badge = view.object
    extras = {}

    try:
        extras["assignments"] = list(
            badge.assignments
                .select_related(
                    "holder_content_type", "site", "assigned_by",
                    "validated_by", "closed_by",
                )
                .order_by("-assigned_at")[:50]
        )
        extras["assignments_total"] = badge.assignments.count()
        extras["active_assignment"] = badge.assignments.filter(
            closed_at__isnull=True,
        ).first()
    except Exception:
        extras["assignments"] = []
        extras["assignments_total"] = 0
        extras["active_assignment"] = None

    try:
        extras["scan_events"] = list(
            badge.scan_events.select_related("site", "access_event")
            .order_by("-timestamp")[:30]
        )
        extras["scans_total"] = badge.scan_events.count()
        extras["scans_granted"] = badge.scan_events.filter(decision="granted").count()
        extras["scans_denied"] = badge.scan_events.filter(decision="denied").count()
    except Exception:
        extras["scan_events"] = []
        extras["scans_total"] = 0
        extras["scans_granted"] = 0
        extras["scans_denied"] = 0

    timeline = []
    if badge.issued_at:
        timeline.append({
            "kind": "issued", "label": "Émission du badge",
            "ts": badge.issued_at,
            "detail": f"UID {badge.uid} · catégorie {badge.get_category_display()}",
        })
    for a in extras["assignments"]:
        timeline.append({
            "kind": "assigned", "label": "Attribué à un porteur",
            "ts": a.assigned_at,
            "detail": a.holder_label,
        })
        if a.released_at:
            timeline.append({
                "kind": "released", "label": "Restitué / libéré",
                "ts": a.released_at,
                "detail": a.holder_label,
            })
    if badge.suspended_at:
        timeline.append({
            "kind": "suspended", "label": "Suspendu",
            "ts": badge.suspended_at,
            "detail": badge.suspended_reason or "Sans motif",
        })
    if badge.revoked_at:
        timeline.append({
            "kind": "revoked", "label": "Révoqué",
            "ts": badge.revoked_at,
            "detail": badge.revoked_reason or "Sans motif",
        })
    timeline.sort(key=lambda x: x["ts"], reverse=True)
    extras["timeline"] = timeline

    extras["pdf_url"] = f"/badges/{badge.id}/pdf/"
    extras["api_base"] = f"/api/v1/devices/badges/{badge.id}"
    return extras


def _company_detail_extras(view, ctx):
    """Injecte compteurs + onglets paginés (employés, ouvriers, sites, visiteurs).

    L'onglet courant est sélectionné via ?tab=employees|workers|sites|visitors,
    avec recherche ?q=… + filtre ?status=active|inactive et pagination ?page=N.
    """
    company = view.object
    request = getattr(view, "request", None)
    GET = request.GET if request else {}
    tab = GET.get("tab", "employees")
    q = (GET.get("q") or "").strip()
    status_filter = GET.get("status", "")

    extras = {"q": q, "status_filter": status_filter}
    extras["tab"] = tab if tab in ("employees", "workers", "sites", "visitors") else "employees"

    try:
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        from administration.views import paginate
        from devices.models import Badge
        from employees.models import Employee
        from ouvriers.models import Worker
        from sites.models import Site
        from visitors.models import Visitor

        # ─── Counters ─────────────────────────────────────────────
        emp_all = Employee.objects.filter(company=company)
        extras["employees_count"] = emp_all.count()
        extras["employees_active"] = emp_all.filter(status="active").count()
        extras["employees_with_badge"] = Badge.objects.filter(
            category="employee_rfid", status__in=("active", "assigned"),
            holder_kind="employee",
            holder_object_id__in=emp_all.values_list("id", flat=True),
        ).count()

        sites_all = Site.objects.filter(company=company)
        extras["sites_count"] = sites_all.count()
        site_ids = list(sites_all.values_list("id", flat=True))

        worker_ids = set()
        if site_ids:
            try:
                from access_control.models import AccessEvent
                worker_ids = set(AccessEvent.objects.filter(
                    site__in=site_ids, holder_kind="worker",
                ).values_list("holder_object_id", flat=True).distinct())
            except Exception:
                logger.warning("Lookup AccessEvent workers échoué (company=%s)",
                                getattr(company, "pk", "?"), exc_info=True)
            try:
                from devices.models import BadgeHelmetPairing
                worker_ids |= set(BadgeHelmetPairing.objects.filter(
                    site__in=site_ids,
                ).values_list("worker_id", flat=True).distinct())
            except Exception:
                logger.warning("Lookup BadgeHelmetPairing workers échoué (company=%s)",
                                getattr(company, "pk", "?"), exc_info=True)
        wk_all = Worker.objects.filter(id__in=worker_ids) if worker_ids else Worker.objects.none()
        extras["workers_count"] = wk_all.count()
        extras["workers_active"] = wk_all.filter(status="active").count()
        extras["workers_with_badge"] = Badge.objects.filter(
            category="worker_rfid", status__in=("active", "assigned"),
            holder_kind="worker",
            holder_object_id__in=list(worker_ids),
        ).count() if worker_ids else 0

        vis_all = Visitor.objects.filter(
            visit_requests__site__in=site_ids,
        ).distinct() if site_ids else Visitor.objects.none()
        extras["visitors_count"] = vis_all.count()
        extras["visitors_recent"] = vis_all.filter(
            visit_requests__created_at__gte=timezone.now() - timedelta(days=30),
        ).distinct().count() if site_ids else 0

        # ─── Onglet actif → queryset filtré + paginé ──────────────
        if extras["tab"] == "employees":
            qs = emp_all.select_related("position", "department")
            if q:
                qs = qs.filter(
                    Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                    Q(matricule__icontains=q) | Q(email__icontains=q)
                )
            if status_filter:
                qs = qs.filter(status=status_filter)
            qs = qs.order_by("last_name", "first_name")
            page_obj, page_qs = paginate(qs, request, per_page=20)
            extras["page_obj"] = page_obj
            extras["employees"] = page_qs
            extras["filtered_count"] = qs.count()
        elif extras["tab"] == "workers":
            qs = wk_all.select_related("trade", "subcontractor")
            if q:
                qs = qs.filter(
                    Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                    Q(matricule__icontains=q)
                )
            if status_filter:
                qs = qs.filter(status=status_filter)
            qs = qs.order_by("last_name", "first_name")
            page_obj, page_qs = paginate(qs, request, per_page=20)
            extras["page_obj"] = page_obj
            extras["workers"] = page_qs
            extras["filtered_count"] = qs.count()
        elif extras["tab"] == "sites":
            qs = sites_all
            if q:
                qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
            if status_filter:
                qs = qs.filter(status=status_filter)
            qs = qs.order_by("name")
            page_obj, page_qs = paginate(qs, request, per_page=20)
            extras["page_obj"] = page_obj
            extras["sites"] = page_qs
            extras["filtered_count"] = qs.count()
        else:  # visitors
            qs = vis_all
            if q:
                qs = qs.filter(
                    Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                    Q(id_number__icontains=q)
                )
            qs = qs.order_by("-created_at")
            page_obj, page_qs = paginate(qs, request, per_page=20)
            extras["page_obj"] = page_obj
            extras["visitors"] = page_qs
            extras["filtered_count"] = qs.count()

    except Exception:
        import logging
        logging.getLogger(__name__).exception("company_detail_extras failed")
        for k in ("employees_count", "employees_active", "employees_with_badge",
                  "sites_count", "workers_count", "workers_active",
                  "workers_with_badge", "visitors_count", "visitors_recent",
                  "filtered_count"):
            extras.setdefault(k, 0)
        extras.setdefault("employees", [])
        extras.setdefault("workers", [])
        extras.setdefault("sites", [])
        extras.setdefault("visitors", [])
        extras.setdefault("page_obj", None)
    return extras


def _holder_movement_extras(holder_kind: str):
    """Factory : retourne un context_extras qui injecte la timeline de scans
    pour un holder (employé / ouvrier / visiteur).
    """
    def _extras(view, ctx):
        from datetime import timedelta

        from django.utils import timezone
        try:
            from devices.models import BadgeScanEvent
        except Exception:
            return {}

        holder = view.object
        events_qs = (BadgeScanEvent.objects
                     .filter(badge__holder_kind=holder_kind,
                             badge__holder_object_id=holder.id)
                     .select_related("badge", "site", "access_event")
                     .order_by("-timestamp"))
        events = list(events_qs[:80])

        since_30d = timezone.now() - timedelta(days=30)
        scans_30d = events_qs.filter(timestamp__gte=since_30d)
        granted_30d = scans_30d.filter(decision="granted").count()
        denied_30d = scans_30d.filter(decision="denied").count()

        sites_visited = list({e.site for e in events if e.site})

        from collections import defaultdict
        seen = defaultdict(set)
        for e in events:
            key = (e.site_id, e.timestamp.date()) if e.site_id else None
            if key:
                if key in seen:
                    e.movement_kind = "out"
                else:
                    e.movement_kind = "in"
                    seen[key].add(True)
            else:
                e.movement_kind = "scan"

        return {
            "movement_events": events,
            "movement_total": events_qs.count(),
            "movement_granted_30d": granted_30d,
            "movement_denied_30d": denied_30d,
            "sites_visited": sites_visited,
            "last_scan": events[0] if events else None,
        }
    return _extras


# ---------------------------------------------------------------------------
# Lazy-load des modèles
# ---------------------------------------------------------------------------
def _build_all():
    from access_control.models import AccessRule
    from ai_assistant.models import AIPromptTemplate
    from antifraud.models import FraudInvestigation, FraudRule
    from attendance.models import (AttendanceCorrection, LeaveRequest,
                                      OvertimeCalculation, OvertimeRule, Roster)
    from audit.models import (ConformityRegister, DataExportRequest,
                                LegalRetentionPolicy)
    from core.models import Company, FeatureFlag, SiteGateway, Tenant
    from devices.models import (Badge, Camera, Device, DeviceMaintenance,
                                   DeviceModel as DM, FirmwareVersion,
                                   Helmet, OTAUpdate)
    from employees.models import Employee
    from mobile_sync.models import MobileDevice
    from notifications.models import NotificationTemplate
    from ouvriers.models import (Crew, Subcontractor, Worker,
                                    WorkerAssignment, WorkerCertification)
    from reports.models import Dashboard, DashboardWidget, Report, ReportSchedule
    from sites.models import Site, Zone
    from visitors.models import (Visitor, VisitorInvitation, VisitorPass,
                                   VisitPurpose, VisitRequest, Watchlist)

    def C(key, **kwargs):
        kwargs.setdefault("url_key", key)
        return key, make_crud(**kwargs)

    pairs = [
        # Identités
        C("employee", model=Employee, form_class=kforms.EmployeeForm,
          active_nav="employees", list_url_name="admin-employees",
          url_prefix="employees", entity_label="Employé", entity_label_plural="Employés",
          detail_template="administration/employee_detail.html",
          detail_context_extras=_holder_movement_extras("employee")),
        C("worker", model=Worker, form_class=kforms.WorkerForm,
          active_nav="workers", list_url_name="admin-workers",
          url_prefix="workers", entity_label="Ouvrier", entity_label_plural="Ouvriers",
          detail_template="administration/worker_detail.html",
          detail_context_extras=_holder_movement_extras("worker")),
        C("subcontractor", model=Subcontractor, form_class=kforms.SubcontractorForm,
          active_nav="workers", list_url_name="admin-workers",
          url_prefix="subcontractors", entity_label="Sous-traitant",
          entity_label_plural="Sous-traitants"),
        C("visitor", model=Visitor, form_class=kforms.VisitorForm,
          active_nav="visitors", list_url_name="admin-visitors",
          url_prefix="visitors", entity_label="Visiteur", entity_label_plural="Visiteurs",
          detail_template="administration/visitor_detail.html",
          detail_context_extras=_holder_movement_extras("visitor")),
        C("visitrequest", model=VisitRequest, form_class=kforms.VisitRequestForm,
          active_nav="visitors", list_url_name="admin-visitors",
          url_prefix="visit-requests", entity_label="Demande de visite",
          entity_label_plural="Demandes de visite"),
        # Terrain
        C("site", model=Site, form_class=kforms.SiteForm,
          active_nav="sites", list_url_name="admin-sites",
          url_prefix="sites", entity_label="Site", entity_label_plural="Sites",
          detail_template="administration/site_detail.html"),
        C("zone", model=Zone, form_class=kforms.ZoneForm,
          active_nav="sites", list_url_name="admin-sites",
          url_prefix="zones", entity_label="Zone", entity_label_plural="Zones"),
        C("device", model=Device, form_class=kforms.DeviceForm,
          active_nav="devices", list_url_name="admin-devices",
          url_prefix="devices", entity_label="Équipement", entity_label_plural="Équipements",
          detail_template="administration/device_detail.html",
          detail_context_extras=_device_detail_extras),
        C("devicemodel", model=DM, form_class=kforms.DeviceModelForm,
          active_nav="devices", list_url_name="admin-devices",
          url_prefix="device-models", entity_label="Modèle d'équipement",
          entity_label_plural="Modèles d'équipements"),
        C("badge", model=Badge, form_class=kforms.BadgeForm,
          active_nav="badges", list_url_name="admin-badges",
          url_prefix="badges", entity_label="Badge", entity_label_plural="Badges",
          detail_template="administration/badge_detail.html",
          detail_context_extras=_badge_detail_extras),
        C("helmet", model=Helmet, form_class=kforms.HelmetForm,
          active_nav="badges", list_url_name="admin-badges",
          url_prefix="helmets", entity_label="Casque", entity_label_plural="Casques"),
        C("camera", model=Camera, form_class=kforms.CameraForm,
          active_nav="cameras", list_url_name="admin-cameras",
          url_prefix="cameras-mng", entity_label="Caméra IP",
          entity_label_plural="Caméras IP"),
        C("gateway", model=SiteGateway, form_class=kforms.SiteGatewayForm,
          active_nav="gateways", list_url_name="admin-gateways",
          url_prefix="gateways", entity_label="Gateway locale",
          entity_label_plural="Gateways locales"),
        # Sécurité
        C("fraudrule", model=FraudRule, form_class=kforms.FraudRuleForm,
          active_nav="antifraud", list_url_name="admin-antifraud",
          url_prefix="fraud-rules", entity_label="Règle anti-fraude",
          entity_label_plural="Règles anti-fraude"),
        # Communication
        C("notiftemplate", model=NotificationTemplate, form_class=kforms.NotificationTemplateForm,
          active_nav="notifications", list_url_name="admin-notifications",
          url_prefix="notification-templates", entity_label="Template de notification",
          entity_label_plural="Templates de notification"),
        # Système — KAYDAN est singleton
        C("tenant", model=Tenant, form_class=kforms.TenantForm,
          active_nav="settings", list_url_name="admin-settings",
          url_prefix="tenants", entity_label="Tenant", entity_label_plural="Tenants"),
        C("company", model=Company, form_class=kforms.CompanyForm,
          active_nav="companies", list_url_name="admin-companies",
          url_prefix="companies", entity_label="Filiale", entity_label_plural="Filiales",
          detail_template="administration/company_detail.html",
          detail_context_extras=_company_detail_extras),
        C("featureflag", model=FeatureFlag, form_class=kforms.FeatureFlagForm,
          active_nav="settings", list_url_name="admin-settings",
          url_prefix="feature-flags", entity_label="Feature flag",
          entity_label_plural="Feature flags"),

        # ===================== Pointage / présence =====================
        C("leaverequest", model=LeaveRequest, form_class=kforms.LeaveRequestForm,
          active_nav="attendance", list_url_name="admin-attendance",
          url_prefix="leave-requests", entity_label="Demande de congé",
          entity_label_plural="Demandes de congés"),
        C("overtimerule", model=OvertimeRule, form_class=kforms.OvertimeRuleForm,
          active_nav="attendance", list_url_name="admin-attendance",
          url_prefix="overtime-rules", entity_label="Règle d'heures sup.",
          entity_label_plural="Règles d'heures sup."),

        # ===================== Audit / conformité =====================
        C("retentionpolicy", model=LegalRetentionPolicy,
          form_class=kforms.LegalRetentionPolicyForm,
          active_nav="audit", list_url_name="admin-audit",
          url_prefix="retention-policies", entity_label="Politique de rétention",
          entity_label_plural="Politiques de rétention"),
        C("dataexport", model=DataExportRequest,
          form_class=kforms.DataExportRequestForm,
          active_nav="audit", list_url_name="admin-audit",
          url_prefix="data-exports", entity_label="Export RGPD",
          entity_label_plural="Exports RGPD"),
        C("conformity", model=ConformityRegister,
          form_class=kforms.ConformityRegisterForm,
          active_nav="audit", list_url_name="admin-audit",
          url_prefix="conformity-registers", entity_label="Registre de conformité",
          entity_label_plural="Registres de conformité"),

        # ===================== Reporting =====================
        C("report", model=Report, form_class=kforms.ReportForm,
          active_nav="reports", list_url_name="admin-reports",
          url_prefix="reports-mng", entity_label="Rapport",
          entity_label_plural="Rapports"),
        C("reportschedule", model=ReportSchedule,
          form_class=kforms.ReportScheduleForm,
          active_nav="reports", list_url_name="admin-reports",
          url_prefix="report-schedules", entity_label="Planification",
          entity_label_plural="Planifications"),

        # ===================== Mobile =====================
        C("mobiledevice", model=MobileDevice, form_class=kforms.MobileDeviceForm,
          active_nav="mobile", list_url_name="admin-mobile",
          url_prefix="mobile-devices", entity_label="Device mobile",
          entity_label_plural="Devices mobiles"),

        # ===================== AI =====================
        C("aitemplate", model=AIPromptTemplate,
          form_class=kforms.AIPromptTemplateForm,
          active_nav="ai", list_url_name="admin-ai",
          url_prefix="ai-templates", entity_label="Prompt IA",
          entity_label_plural="Prompts IA"),

        # ===================== Workflow visiteurs (P0) =====================
        C("visitpurpose", model=VisitPurpose, form_class=kforms.VisitPurposeForm,
          active_nav="visitors", list_url_name="admin-visitors",
          url_prefix="visit-purposes", entity_label="Motif de visite",
          entity_label_plural="Motifs de visite"),
        C("visitorpass", model=VisitorPass, form_class=kforms.VisitorPassForm,
          active_nav="visitors", list_url_name="admin-visitors",
          url_prefix="visitor-passes", entity_label="Pass visiteur",
          entity_label_plural="Pass visiteurs"),
        C("watchlist", model=Watchlist, form_class=kforms.WatchlistForm,
          active_nav="visitors", list_url_name="admin-visitors",
          url_prefix="watchlists", entity_label="Liste rouge",
          entity_label_plural="Liste rouge"),
        C("visitorinvitation", model=VisitorInvitation,
          form_class=kforms.VisitorInvitationForm,
          active_nav="visitors", list_url_name="admin-visitors",
          url_prefix="visit-invitations", entity_label="Invitation",
          entity_label_plural="Invitations"),

        # ===================== Fraude (P0 #2) =====================
        C("fraudinvestigation", model=FraudInvestigation,
          form_class=kforms.FraudInvestigationForm,
          active_nav="antifraud", list_url_name="admin-antifraud",
          url_prefix="fraud-investigations", entity_label="Enquête anti-fraude",
          entity_label_plural="Enquêtes anti-fraude"),

        # ===================== AccessRule (P0 #3) =====================
        C("accessrule", model=AccessRule, form_class=kforms.AccessRuleForm,
          active_nav="access", list_url_name="admin-access-rules",
          url_prefix="access-rules", entity_label="Règle d'accès",
          entity_label_plural="Règles d'accès"),

        # ===================== Dashboards configurables (P3) =====================
        C("dashboard", model=Dashboard, form_class=kforms.DashboardForm,
          active_nav="reports", list_url_name="admin-reports",
          url_prefix="dashboards", entity_label="Dashboard",
          entity_label_plural="Dashboards"),
        C("dashwidget", model=DashboardWidget,
          form_class=kforms.DashboardWidgetForm,
          active_nav="reports", list_url_name="admin-reports",
          url_prefix="dashboard-widgets", entity_label="Widget",
          entity_label_plural="Widgets"),

        # ===================== Devices monitoring — P1 #4 =====================
        C("devicemaint", model=DeviceMaintenance,
          form_class=kforms.DeviceMaintenanceForm,
          active_nav="devices", list_url_name="admin-devices",
          url_prefix="device-maintenances", entity_label="Maintenance device",
          entity_label_plural="Maintenances devices"),
        C("firmware", model=FirmwareVersion,
          form_class=kforms.FirmwareVersionForm,
          active_nav="devices", list_url_name="admin-devices",
          url_prefix="firmwares", entity_label="Firmware",
          entity_label_plural="Firmwares"),
        C("ota", model=OTAUpdate, form_class=kforms.OTAUpdateForm,
          active_nav="devices", list_url_name="admin-devices",
          url_prefix="ota-updates", entity_label="Update OTA",
          entity_label_plural="Updates OTA"),

        # ===================== Pointage RH — P1 #2 =====================
        C("attendancecorrection", model=AttendanceCorrection,
          form_class=kforms.AttendanceCorrectionForm,
          active_nav="attendance", list_url_name="admin-attendance",
          url_prefix="attendance-corrections", entity_label="Correction pointage",
          entity_label_plural="Corrections pointage"),
        C("roster", model=Roster, form_class=kforms.RosterForm,
          active_nav="attendance", list_url_name="admin-attendance",
          url_prefix="rosters", entity_label="Planning",
          entity_label_plural="Plannings"),
        C("overtimecalc", model=OvertimeCalculation,
          form_class=kforms.OvertimeCalculationForm,
          active_nav="attendance", list_url_name="admin-attendance",
          url_prefix="overtime-calcs", entity_label="Calcul HS",
          entity_label_plural="Calculs HS"),

        # ===================== Workers — P1 #1 =====================
        C("workercert", model=WorkerCertification,
          form_class=kforms.WorkerCertificationForm,
          active_nav="workers", list_url_name="admin-workers",
          url_prefix="worker-certifications", entity_label="Certification ouvrier",
          entity_label_plural="Certifications ouvriers"),
        C("crew", model=Crew, form_class=kforms.CrewForm,
          active_nav="workers", list_url_name="admin-workers",
          url_prefix="crews", entity_label="Équipe chantier",
          entity_label_plural="Équipes chantier"),
        C("workerassignment", model=WorkerAssignment,
          form_class=kforms.WorkerAssignmentForm,
          active_nav="workers", list_url_name="admin-workers",
          url_prefix="worker-assignments", entity_label="Affectation ouvrier",
          entity_label_plural="Affectations ouvriers"),
    ]
    return dict(pairs)


_CACHE = None


def get_cruds():
    """Retourne le dict des CRUD (lazy-loaded au premier appel)."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _build_all()
    return _CACHE
