"""KAYDAN SHIELD — Routes du back-office d'administration."""
from django.urls import path

from . import views
from .crud_views import get_cruds


def crud_paths(prefix: str, key: str):
    """Génère les 4 routes CRUD pour une entité."""
    cruds = get_cruds()
    crud = cruds[key]
    return [
        path(f"{prefix}/new/",            crud.Create.as_view(), name=f"admin-{key}-create"),
        path(f"{prefix}/<int:pk>/",       crud.Detail.as_view(), name=f"admin-{key}-detail"),
        path(f"{prefix}/<int:pk>/edit/",  crud.Update.as_view(), name=f"admin-{key}-update"),
        path(f"{prefix}/<int:pk>/delete/",crud.Delete.as_view(), name=f"admin-{key}-delete"),
    ]


urlpatterns = [
    # Pilotage
    path("",                  views.DashboardView.as_view(),     name="admin-dashboard"),
    path("home/",             views.AdminHomeView.as_view(),     name="home"),
    path("realtime/",         views.RealtimeView.as_view(),      name="admin-realtime"),
    path("realtime/export/",  views.RealtimeExportView.as_view(), name="admin-realtime-export"),
    path("map/",              views.MapView.as_view(),           name="admin-map"),
    path("map/data/",         views.MapDataAPIView.as_view(),    name="admin-map-data"),

    # Identités — listes
    path("employees/",        views.EmployeesView.as_view(),     name="admin-employees"),
    path("face-test/",        views.FaceRecognitionTestView.as_view(), name="admin-face-test"),
    path("workers/",          views.WorkersView.as_view(),       name="admin-workers"),
    path("visitors/",         views.VisitorsView.as_view(),      name="admin-visitors"),

    # Terrain — listes
    path("sites/",            views.SitesView.as_view(),         name="admin-sites"),
    path("devices/",          views.DevicesView.as_view(),       name="admin-devices"),
    path("badges/",           views.BadgesView.as_view(),        name="admin-badges"),
    path("badges/scan/",      views.BadgeScanView.as_view(),     name="admin-badge-scan"),
    path("gateways/",         views.GatewaysView.as_view(),      name="admin-gateways"),

    # Sécurité — listes
    path("attendance/",       views.AttendanceView.as_view(),    name="admin-attendance"),
    path("antifraud/",        views.AntifraudView.as_view(),     name="admin-antifraud"),
    path("audit/",            views.AuditView.as_view(),         name="admin-audit"),

    # Communication — listes
    path("notifications/",    views.NotificationsView.as_view(), name="admin-notifications"),
    path("mobile/",           views.MobileSyncView.as_view(),    name="admin-mobile"),

    # Reporting — listes
    path("reports/",          views.ReportsView.as_view(),       name="admin-reports"),
    path("ai/",               views.AIAssistantView.as_view(),   name="admin-ai"),

    # Système — listes
    path("accounts/",         views.AccountsView.as_view(),      name="admin-accounts"),
    path("companies/",        views.CompaniesView.as_view(),     name="admin-companies"),
    path("settings/",         views.SettingsView.as_view(),      name="admin-settings"),

    # ====================== CRUD per entity ======================
    *crud_paths("employees",            "employee"),
    *crud_paths("workers",              "worker"),
    *crud_paths("subcontractors",       "subcontractor"),
    *crud_paths("visitors-mng",         "visitor"),
    *crud_paths("visit-requests",       "visitrequest"),

    *crud_paths("sites-mng",            "site"),
    *crud_paths("zones",                "zone"),
    *crud_paths("devices-mng",          "device"),
    *crud_paths("device-models",        "devicemodel"),
    *crud_paths("badges-mng",           "badge"),
    *crud_paths("helmets",              "helmet"),
    *crud_paths("gateways-mng",         "gateway"),

    *crud_paths("fraud-rules",          "fraudrule"),

    *crud_paths("notification-templates", "notiftemplate"),

    *crud_paths("companies-mng",        "company"),
    *crud_paths("feature-flags",        "featureflag"),

    # Pointage
    *crud_paths("leave-requests",       "leaverequest"),
    *crud_paths("overtime-rules",       "overtimerule"),

    # Audit
    *crud_paths("retention-policies",   "retentionpolicy"),
    *crud_paths("data-exports",         "dataexport"),
    *crud_paths("conformity-registers", "conformity"),

    # Reporting
    *crud_paths("reports-mng",          "report"),
    *crud_paths("report-schedules",     "reportschedule"),

    # Mobile
    *crud_paths("mobile-devices",       "mobiledevice"),

    # AI
    *crud_paths("ai-templates",         "aitemplate"),

    # ───── Gestion utilisateurs (vues natives KAYDAN) ─────
    path("accounts/new/",                 views.UserCreateView.as_view(),    name="admin-user-create"),
    path("accounts/<int:pk>/",            views.UserDetailView.as_view(),    name="admin-user-detail"),
    path("accounts/<int:pk>/edit/",       views.UserUpdateView.as_view(),    name="admin-user-update"),
    path("accounts/<int:pk>/password/",   views.UserPasswordView.as_view(),  name="admin-user-password"),
    path("accounts/<int:pk>/toggle/",     views.UserToggleActiveView.as_view(), name="admin-user-toggle"),

    # Rôles
    path("roles/",                  views.RoleListView.as_view(),    name="admin-roles"),
    path("roles/new/",              views.RoleCreateView.as_view(),  name="admin-role-create"),
    path("roles/<int:pk>/edit/",    views.RoleUpdateView.as_view(),  name="admin-role-update"),

    # ───── Clés API IoT ─────
    path("api-keys/",               views.APIKeyListView.as_view(),    name="admin-api-keys"),
    path("api-keys/new/",           views.APIKeyCreateView.as_view(),  name="admin-api-key-create"),
    path("api-keys/<int:pk>/revoke/", views.APIKeyRevokeView.as_view(), name="admin-api-key-revoke"),

    # ───── Mini-API notifications (consommée par la topbar) ─────
    path("api/notifications/unread/",
         views.NotificationUnreadCountView.as_view(), name="admin-notif-unread"),
    path("api/notifications/recent/",
         views.NotificationRecentView.as_view(), name="admin-notif-recent"),
    path("api/notifications/mark-all-read/",
         views.NotificationMarkAllReadView.as_view(), name="admin-notif-mark-all-read"),
]

# ===== Singleton tenant KAYDAN — édition seule =====
from .crud_views import get_cruds as _get_cruds
_tenant_crud = _get_cruds()["tenant"]
urlpatterns += [
    path("kaydan/<int:pk>/",       _tenant_crud.Detail.as_view(), name="admin-tenant-detail"),
    path("kaydan/<int:pk>/edit/",  _tenant_crud.Update.as_view(), name="admin-tenant-update"),
]
