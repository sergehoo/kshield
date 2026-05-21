"""Vues SSO — login init, callback, logout, status, offline-login."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

logger = logging.getLogger(__name__)


class SSOLoginView(View):
    """GET /sso/login/ → redirige vers Keycloak.

    Si SSO_ENABLED=False ou mozilla-django-oidc absent, fallback vers le login
    local KAYDAN existant.
    """

    def get(self, request):
        if not getattr(settings, "SSO_ENABLED", False):
            return redirect("admin-login")
        try:
            from mozilla_django_oidc.views import OIDCAuthenticationRequestView
            return OIDCAuthenticationRequestView.as_view()(request)
        except ImportError:
            return redirect("admin-login")


class SSOCallbackView(View):
    """GET /sso/callback/?code=…&state=… — délègue à mozilla-django-oidc."""

    def get(self, request):
        try:
            from mozilla_django_oidc.views import OIDCAuthenticationCallbackView
            return OIDCAuthenticationCallbackView.as_view()(request)
        except ImportError:
            return redirect("admin-login")


class SSOLogoutView(View):
    """Logout global : déconnexion Django + invalidation côté Keycloak."""

    def get(self, request):
        return self.post(request)

    def post(self, request):
        from django.contrib.auth import logout

        # Récupère le refresh_token AVANT logout pour révoquer côté Keycloak
        refresh = request.session.get("oidc_refresh_token") or request.session.get("refresh_token", "")
        session_state = request.session.get("oidc_session_state", "")

        # Logout Django (vide la session)
        logout(request)

        # Trace l'audit
        try:
            from sso.models import SSOLoginAudit
            SSOLoginAudit.objects.create(kind="logout", success=True)
        except Exception:
            logger.warning("SSOLoginAudit logout non tracé", exc_info=True)

        # Marque la SSOSession comme logged_out
        if session_state:
            try:
                from sso.services import revoke_session
                revoke_session(session_state, reason="user_logout")
            except Exception:
                logger.debug("revoke_session failed", exc_info=True)

        # Tente d'appeler le logout endpoint Keycloak (révoque le refresh côté serveur)
        if refresh and getattr(settings, "OIDC_OP_LOGOUT_ENDPOINT", ""):
            try:
                import requests
                requests.post(
                    settings.OIDC_OP_LOGOUT_ENDPOINT,
                    data={
                        "client_id": settings.OIDC_RP_CLIENT_ID,
                        "client_secret": getattr(settings, "OIDC_RP_CLIENT_SECRET", ""),
                        "refresh_token": refresh,
                    },
                    timeout=3,
                )
            except Exception:
                logger.debug("Logout Keycloak request failed", exc_info=True)

        # Redirige vers la page login KAYDAN OU vers le logout endpoint Keycloak
        # qui termine aussi la session SSO (single logout).
        end_session = getattr(settings, "OIDC_OP_LOGOUT_ENDPOINT", "")
        post_logout = getattr(settings, "LOGOUT_REDIRECT_URL", "/auth/login/")
        if end_session:
            params = urlencode({
                "post_logout_redirect_uri": request.build_absolute_uri(post_logout),
                "client_id": settings.OIDC_RP_CLIENT_ID,
            })
            return redirect(f"{end_session}?{params}")
        return redirect(post_logout)


class SSOStatusView(View):
    """GET /sso/status/ → JSON avec l'état SSO du user courant."""

    def get(self, request):
        out = {
            "sso_enabled": bool(getattr(settings, "SSO_ENABLED", False)),
            "authenticated": request.user.is_authenticated,
        }
        if request.user.is_authenticated:
            out["user"] = {
                "email": request.user.email,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "is_superuser": request.user.is_superuser,
            }
            try:
                ident = request.user.sso_identity
                out["sso"] = {
                    "subject": ident.subject,
                    "issuer": ident.issuer,
                    "preferred_username": ident.preferred_username,
                    "federation_provider": ident.federation_provider,
                }
            except Exception:
                out["sso"] = None
        return JsonResponse(out)


class SSOErrorView(View):
    """Page rendue si Keycloak retourne une erreur dans le callback."""

    def get(self, request):
        return render(request, "sso/error.html", {
            "error": request.GET.get("error", "unknown"),
            "description": request.GET.get("error_description", ""),
        })


class SSOOfflineLoginView(View):
    """Login d'urgence sur une gateway edge sans connectivité Keycloak.

    POST { "email": "...", "pin": "1234", "site_id": 7 }
    Vérifie OfflineUserCredentialCache et retourne un cookie session local.
    """

    def post(self, request):
        from django.contrib.auth import login

        from sso.models import OfflineUserCredentialCache, SSOLoginAudit
        from sso.utils import hash_pin

        email = (request.POST.get("email") or "").strip().lower()
        pin = (request.POST.get("pin") or "").strip()
        site_id = request.POST.get("site_id")

        if not (email and pin and site_id):
            return JsonResponse({"error": "Champs requis : email, pin, site_id"},
                                 status=400)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return JsonResponse({"error": "Identifiants invalides"}, status=401)

        try:
            cache = OfflineUserCredentialCache.objects.get(
                user=user, site_id=site_id, is_active=True,
            )
        except OfflineUserCredentialCache.DoesNotExist:
            SSOLoginAudit.objects.create(
                user=user, email=email, kind="offline_login", success=False,
                reason="Pas de cache pour cet utilisateur sur ce site",
                ip=request.META.get("REMOTE_ADDR"),
            )
            return JsonResponse({"error": "Identifiants invalides"}, status=401)

        from django.utils import timezone as tz
        if cache.expires_at < tz.now():
            return JsonResponse({"error": "Cache offline expiré, reconnectez-vous au serveur central"},
                                 status=401)

        if not cache.pin_hash or cache.pin_hash != hash_pin(pin):
            SSOLoginAudit.objects.create(
                user=user, email=email, kind="offline_login", success=False,
                reason="PIN invalide", ip=request.META.get("REMOTE_ADDR"),
                site_id=site_id,
            )
            return JsonResponse({"error": "Identifiants invalides"}, status=401)

        # Login Django local
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        SSOLoginAudit.objects.create(
            user=user, email=email, kind="offline_login", success=True,
            ip=request.META.get("REMOTE_ADDR"), site_id=site_id,
        )
        return JsonResponse({
            "ok": True,
            "permissions": cache.permissions_snapshot,
            "expires_at": cache.expires_at.isoformat(),
        })


class SSOMeAPIView(View):
    """GET /api/sso/me/ — claims + perms du user courant (utilisé par mobile)."""

    def get(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Not authenticated"}, status=401)
        from accounts.rbac import user_permissions
        ident = getattr(request.user, "sso_identity", None)
        return JsonResponse({
            "id": request.user.id,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "is_superuser": request.user.is_superuser,
            "subject": ident.subject if ident else None,
            "permissions": sorted(user_permissions(request.user)),
        })


class SSOEdgeSyncAPIView(View):
    """POST /api/sso/edge/sync/ — déclenche la synchro des users vers une gateway.

    Auth : HMAC API key (déjà existant pour /api/v1/access/scan/).
    Body : { "site_id": 7, "ttl_hours": 24 }
    Réponse : liste des users à cacher localement (sans password en clair).
    """

    def post(self, request):
        from accounts.hmac_auth import HMACAPIKeyAuthentication
        # Authentification HMAC manuelle (View générique, pas DRF)
        auth = HMACAPIKeyAuthentication()
        try:
            result = auth.authenticate(request)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=401)
        if result is None:
            return JsonResponse({"error": "Signature HMAC requise"}, status=401)

        import json
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "JSON invalide"}, status=400)

        site_id = body.get("site_id")
        ttl = int(body.get("ttl_hours", 24))
        if not site_id:
            return JsonResponse({"error": "site_id requis"}, status=400)

        try:
            from sites.models import Site
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist:
            return JsonResponse({"error": "Site introuvable"}, status=404)

        from sso.services import sync_users_to_edge
        result = sync_users_to_edge(site, ttl_hours=ttl)
        return JsonResponse({
            "site_id": site.id,
            "site_code": site.code,
            "pushed": result["pushed"],
            "revoked": result["revoked"],
            "expires_at": result["expires_at"].isoformat(),
        })


class SSOEdgeRosterAPIView(View):
    """GET /api/sso/edge/roster/?site_id=7 — liste des users cachés sur une gateway.

    Utilisé par la borne edge au démarrage pour récupérer les credentials offline.
    """

    def get(self, request):
        from accounts.hmac_auth import HMACAPIKeyAuthentication
        auth = HMACAPIKeyAuthentication()
        try:
            result = auth.authenticate(request)
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=401)
        if result is None:
            return JsonResponse({"error": "Signature HMAC requise"}, status=401)

        site_id = request.GET.get("site_id")
        if not site_id:
            return JsonResponse({"error": "site_id requis"}, status=400)

        from sso.models import OfflineUserCredentialCache
        users = []
        qs = (OfflineUserCredentialCache.objects
              .filter(site_id=site_id, is_active=True)
              .select_related("user"))
        for c in qs:
            users.append({
                "user_id": c.user_id,
                "email": c.user.email,
                "first_name": c.user.first_name,
                "last_name": c.user.last_name,
                # On envoie le hash bcrypt — la borne valide via la lib Django
                "password_hash": c.password_hash,
                "pin_hash": c.pin_hash,
                "badge_uid": c.badge_uid,
                "permissions": c.permissions_snapshot or [],
                "expires_at": c.expires_at.isoformat(),
            })
        return JsonResponse({"site_id": int(site_id), "users": users,
                              "count": len(users)})


class SSOTokenVerifyAPIView(View):
    """POST /api/sso/token/verify/ — utilitaire pour les apps tierces."""

    def post(self, request):
        token = request.POST.get("token") or ""
        if not token:
            return JsonResponse({"valid": False, "error": "Token requis"}, status=400)
        try:
            from sso.utils import decode_jwt
            claims = decode_jwt(token)
            return JsonResponse({"valid": True, "sub": claims.get("sub"),
                                 "exp": claims.get("exp")})
        except Exception as exc:
            return JsonResponse({"valid": False, "error": str(exc)[:200]})
