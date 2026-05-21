"""URLs SSO — pluggables sur /sso/* et /api/sso/*."""
from django.urls import path

from . import views

app_name = "sso"

urlpatterns = [
    path("login/",         views.SSOLoginView.as_view(),      name="login"),
    path("callback/",      views.SSOCallbackView.as_view(),   name="callback"),
    path("logout/",        views.SSOLogoutView.as_view(),     name="logout"),
    path("status/",        views.SSOStatusView.as_view(),     name="status"),
    path("error/",         views.SSOErrorView.as_view(),      name="error"),
    path("offline-login/", views.SSOOfflineLoginView.as_view(), name="offline_login"),
]

api_urlpatterns = [
    path("me/",            views.SSOMeAPIView.as_view(),         name="me"),
    path("token/verify/",  views.SSOTokenVerifyAPIView.as_view(), name="token_verify"),
    path("edge/sync/",     views.SSOEdgeSyncAPIView.as_view(),    name="edge_sync"),
    path("edge/roster/",   views.SSOEdgeRosterAPIView.as_view(),  name="edge_roster"),
]
