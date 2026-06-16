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
    path("system/",           views.SystemStatusView.as_view(),  name="admin-system-status"),
    path("devices/",          views.DevicesView.as_view(),       name="admin-devices"),
    # Assistant 2-étapes "Ajouter un lecteur" (picker techno → form pré-filtré)
    path("devices/add/",      views.DeviceReaderPickerView.as_view(),
         name="admin-device-reader-picker"),
    path("devices/add/<str:kind>/",  views.DeviceReaderCreateView.as_view(),
         name="admin-device-reader-create"),
    path("cameras/",          views.CamerasView.as_view(),       name="admin-cameras"),
    path("cameras/live/",     views.CamerasLiveView.as_view(),   name="admin-cameras-live"),
    path("cameras/presence/", views.FacePresenceView.as_view(),  name="admin-face-presence"),
    path("badges/",           views.BadgesView.as_view(),        name="admin-badges"),
    path("badges/enroll/",    views.BadgeEnrollmentView.as_view(),name="admin-badge-enroll"),
    path("badges/scan/",      views.BadgeScanView.as_view(),     name="admin-badge-scan"),
    path("gateways/",         views.GatewaysView.as_view(),      name="admin-gateways"),

    # Sécurité — listes
    path("attendance/",       views.AttendanceView.as_view(),    name="admin-attendance"),
    path("attendance/sheet/export/", views.AttendanceSheetExportView.as_view(),
         name="admin-attendance-sheet-export"),
    path("antifraud/",        views.AntifraudView.as_view(),     name="admin-antifraud"),
    path("audit/",            views.AuditView.as_view(),         name="admin-audit"),

    # Communication — listes
    path("notifications/",    views.NotificationsView.as_view(), name="admin-notifications"),
    path("mobile/",           views.MobileSyncView.as_view(),    name="admin-mobile"),

    # Reporting — listes
    path("reports/",          views.ReportsView.as_view(),       name="admin-reports"),
    path("digests/",          views.ExecutiveDigestListView.as_view(),
                                                                  name="admin-digests"),
    path("digests/<int:pk>/", views.ExecutiveDigestDetailView.as_view(),
                                                                  name="admin-digest-detail"),
    path("digests/action/<str:verb>/",
         views.ExecutiveDigestActionView.as_view(),
                                                                  name="admin-digest-action"),
    path("digests/<int:pk>/action/<str:verb>/",
         views.ExecutiveDigestActionView.as_view(),
                                                                  name="admin-digest-item-action"),
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
    *crud_paths("cameras-mng",          "camera"),
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

    # Workflow visiteurs (P0)
    *crud_paths("visit-purposes",       "visitpurpose"),
    *crud_paths("visitor-passes",       "visitorpass"),
    *crud_paths("watchlists",           "watchlist"),
    *crud_paths("visit-invitations",    "visitorinvitation"),

    # Fraude — investigations (P0)
    *crud_paths("fraud-investigations", "fraudinvestigation"),

    # Access rules (P0)
    *crud_paths("access-rules",         "accessrule"),
    path("access-rules/",
         views.AccessRulesView.as_view(), name="admin-access-rules"),

    # ───── Actions métier visiteurs (P0) ─────
    path("visit-requests/<int:pk>/action/<str:verb>/",
         views.VisitRequestActionView.as_view(), name="admin-visitrequest-action"),
    path("visitors-mng/<int:pk>/watchlist/",
         views.VisitorAddToWatchlistView.as_view(), name="admin-visitor-watchlist-add"),

    # ───── P3 — Calendrier ICS visite ─────
    path("visit-requests/<int:pk>/calendar.ics",
         views.VisitCalendarICSView.as_view(), name="admin-visit-ics"),

    # ───── Actions métier fraude (P0) ─────
    path("antifraud-alerts/<int:pk>/action/<str:verb>/",
         views.FraudAlertActionView.as_view(), name="admin-fraudalert-action"),

    # ───── P1 #1 — Workers complets ─────
    *crud_paths("worker-certifications", "workercert"),
    *crud_paths("crews",                 "crew"),
    *crud_paths("worker-assignments",    "workerassignment"),

    # ───── P1 #2 — Pointage RH ─────
    *crud_paths("attendance-corrections", "attendancecorrection"),
    *crud_paths("rosters",                "roster"),
    *crud_paths("overtime-calcs",         "overtimecalc"),

    # ───── P1 #3 — RGPD : génération ZIP export ─────
    path("data-exports/<int:pk>/generate/",
         views.DataExportGenerateView.as_view(), name="admin-dataexport-generate"),

    # ───── P1 #4 — Devices monitoring ─────
    *crud_paths("device-maintenances", "devicemaint"),
    *crud_paths("firmwares",           "firmware"),
    *crud_paths("ota-updates",         "ota"),

    # ───── P3 — Dashboards configurables ─────
    *crud_paths("dashboards",          "dashboard"),
    *crud_paths("dashboard-widgets",   "dashwidget"),

    # ───── Auth (login/logout custom) ─────
    path("auth/login/",  views.KshieldLoginView.as_view(),  name="admin-login"),
    path("auth/logout/", views.KshieldLogoutView.as_view(), name="admin-logout"),

    # ───── P2 — Imports CSV en masse ─────
    path("import/<str:kind>/", views.CSVImportView.as_view(), name="admin-csv-import"),

    # ───── Profil utilisateur courant (sidebar dropdown) ─────
    path("me/",          views.MyProfileRedirectView.as_view(),
         {"verb": "detail"}, name="admin-me"),
    path("me/edit/",     views.MyProfileRedirectView.as_view(),
         {"verb": "update"}, name="admin-me-edit"),
    path("me/password/", views.MyProfileRedirectView.as_view(),
         {"verb": "password"}, name="admin-me-password"),

    # ───── Gestion utilisateurs (vues natives KAYDAN) ─────
    path("accounts/new/",                 views.UserCreateView.as_view(),    name="admin-user-create"),
    path("accounts/<int:pk>/",            views.UserDetailView.as_view(),    name="admin-user-detail"),
    path("accounts/<int:pk>/edit/",       views.UserUpdateView.as_view(),    name="admin-user-update"),
    path("accounts/<int:pk>/password/",   views.UserPasswordView.as_view(),  name="admin-user-password"),
    path("accounts/<int:pk>/toggle/",     views.UserToggleActiveView.as_view(), name="admin-user-toggle"),
    path("accounts/<int:pk>/delete/",     views.UserDeleteView.as_view(),    name="admin-user-delete"),

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


# ===== Camera Create personnalisée — accepte ?rtsp_url=&name=... en query =====
# Permet au "Scanner le réseau (ONVIF)" de pré-remplir le formulaire.
# Doit être défini APRÈS la création de toutes les routes pour override.
_camera_crud = _get_cruds()["camera"]


class _CameraPrefillCreateView(_camera_crud.Create):
    """CreateView qui pré-remplit le form depuis les query params URL."""

    PREFILL_FIELDS = (
        "rtsp_url", "name", "username", "location_label",
        "transport", "codec",
    )

    def get_initial(self):
        initial = super().get_initial()
        for key in self.PREFILL_FIELDS:
            v = self.request.GET.get(key)
            if v:
                initial[key] = v
        return initial


# Override : on insère AVANT les patterns existants pour qu'il gagne le matching
urlpatterns.insert(0, path(
    "cameras-mng/new/",
    _CameraPrefillCreateView.as_view(),
    name="admin-camera-create",
))
