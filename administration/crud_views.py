"""KAYDAN SHIELD — Vues CRUD génériques pour le back-office.

Pattern : pour chaque entité, on définit une `EntityCRUD` qui regroupe
list / detail / create / update / delete avec un layout unifié.

`make_crud()` prend un dict de config et retourne 4 classes
(Create / Detail / Update / Delete) prêtes à câbler dans `urls.py`.
"""
from __future__ import annotations

from typing import Optional

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, UpdateView

from . import forms as kforms


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
                pass
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Mixin commun
# ---------------------------------------------------------------------------
class AdminContextMixin:
    """Pose les variables consommées par templates/layout/base.html."""

    active_nav: str = ""
    page_title: str = ""
    breadcrumb: str = ""
    list_url_name: str = ""
    entity_label: str = "Élément"
    entity_label_plural: str = "Éléments"

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

        def get_context_data(self, **kwargs):
            ctx = super().get_context_data(**kwargs)
            ctx["url_key"] = _url_key
            return ctx

    class _Detail(AdminContextMixin, DetailView):
        template_name = detail_template or "administration/_detail.html"

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
            out = []
            for f in self.object._meta.get_fields():
                if f.is_relation and f.many_to_many:
                    try:
                        vals = list(getattr(self.object, f.name).all()[:5])
                        val = ", ".join(str(v) for v in vals) if vals else None
                    except Exception:
                        val = None
                elif f.is_relation and f.one_to_many:
                    continue
                elif f.is_relation:
                    try: val = getattr(self.object, f.name, None)
                    except Exception: val = None
                else:
                    val = getattr(self.object, f.name, None)
                if hasattr(f, "verbose_name"):
                    label = str(f.verbose_name).capitalize()
                else:
                    label = f.name.replace("_", " ").capitalize()
                out.append((label, val))
            return out

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
def _badge_detail_extras(view, ctx):
    """Injecte timeline (assignments + scans) pour le badge detail."""
    badge = view.object
    extras = {}

    try:
        extras["assignments"] = list(
            badge.assignments
                .select_related("visit_request", "assigned_by", "released_by")
                .order_by("-assigned_at")[:50]
        )
        extras["assignments_total"] = badge.assignments.count()
        extras["active_assignment"] = badge.assignments.filter(
            released_at__isnull=True,
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
    """Injecte les compteurs (employés, ouvriers, visiteurs) + sites pour la
    fiche détail d'une filiale.
    """
    company = view.object
    extras = {}
    try:
        from devices.models import Badge
        from employees.models import Employee
        from ouvriers.models import Worker
        from sites.models import Site
        from visitors.models import Visitor, VisitRequest

        emp_qs = Employee.objects.filter(company=company)
        extras["employees_count"] = emp_qs.count()
        extras["employees_active"] = emp_qs.filter(status="active").count()
        extras["employees_with_badge"] = Badge.objects.filter(
            category="employee_rfid", status__in=("active", "assigned"),
            holder_kind="employee",
            holder_object_id__in=emp_qs.values_list("id", flat=True),
        ).count()

        sites_qs = Site.objects.filter(company=company)
        extras["sites_count"] = sites_qs.count()
        extras["sites_list"] = list(sites_qs.order_by("name")[:8])

        site_ids = list(sites_qs.values_list("id", flat=True))
        worker_ids = set()
        if site_ids:
            try:
                from access_control.models import AccessEvent
                worker_ids = set(AccessEvent.objects.filter(
                    site__in=site_ids, holder_kind="worker",
                ).values_list("holder_object_id", flat=True).distinct())
            except Exception:
                pass
            try:
                from devices.models import BadgeHelmetPairing
                worker_ids |= set(BadgeHelmetPairing.objects.filter(
                    site__in=site_ids,
                ).values_list("worker_id", flat=True).distinct())
            except Exception:
                pass
        wk_qs = Worker.objects.filter(id__in=worker_ids) if worker_ids else Worker.objects.none()
        extras["workers_count"] = wk_qs.count()
        extras["workers_active"] = wk_qs.filter(status="active").count()
        extras["workers_with_badge"] = Badge.objects.filter(
            category="worker_rfid", status__in=("active", "assigned"),
            holder_kind="worker",
            holder_object_id__in=worker_ids,
        ).count() if worker_ids else 0

        vis_qs = Visitor.objects.filter(
            visit_requests__site__in=site_ids,
        ).distinct() if site_ids else Visitor.objects.none()
        extras["visitors_count"] = vis_qs.count()
        from datetime import timedelta

        from django.utils import timezone
        extras["visitors_recent"] = vis_qs.filter(
            visit_requests__created_at__gte=timezone.now() - timedelta(days=30),
        ).distinct().count() if site_ids else 0

        extras["top_employees"] = list(
            emp_qs.order_by("-created_at").select_related("position", "department")[:5]
        )
        extras["top_workers"] = list(
            wk_qs.order_by("-created_at").select_related("trade", "subcontractor")[:5]
        ) if worker_ids else []
    except Exception:
        import logging
        logging.getLogger(__name__).exception("company_detail_extras failed")
        for k in ("employees_count", "employees_active", "employees_with_badge",
                  "sites_count", "workers_count", "workers_active",
                  "workers_with_badge", "visitors_count", "visitors_recent"):
            extras.setdefault(k, 0)
        extras.setdefault("sites_list", [])
        extras.setdefault("top_employees", [])
        extras.setdefault("top_workers", [])
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
    from antifraud.models import FraudRule
    from core.models import Company, FeatureFlag, SiteGateway, Tenant
    from devices.models import Badge, Device, DeviceModel as DM, Helmet
    from employees.models import Employee
    from notifications.models import NotificationTemplate
    from ouvriers.models import Subcontractor, Worker
    from sites.models import Site, Zone
    from visitors.models import Visitor, VisitRequest

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
          url_prefix="sites", entity_label="Site", entity_label_plural="Sites"),
        C("zone", model=Zone, form_class=kforms.ZoneForm,
          active_nav="sites", list_url_name="admin-sites",
          url_prefix="zones", entity_label="Zone", entity_label_plural="Zones"),
        C("device", model=Device, form_class=kforms.DeviceForm,
          active_nav="devices", list_url_name="admin-devices",
          url_prefix="devices", entity_label="Équipement", entity_label_plural="Équipements"),
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
    ]
    return dict(pairs)


_CACHE = None


def get_cruds():
    """Retourne le dict des CRUD (lazy-loaded au premier appel)."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _build_all()
    return _CACHE
