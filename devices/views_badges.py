"""KAYDAN SHIELD — API cycle de vie badges (Phase 3 refonte).

Endpoints exposés :

  POST /api/v1/devices/badges/<id>/assign/
  POST /api/v1/devices/badges/<id>/unassign/
  POST /api/v1/devices/badges/<id>/suspend/
  POST /api/v1/devices/badges/<id>/resume/
  POST /api/v1/devices/badges/<id>/expire/
  POST /api/v1/devices/badges/<id>/report-lost/
  POST /api/v1/devices/badges/<id>/report-stolen/
  POST /api/v1/devices/badges/<id>/disable/
  POST /api/v1/devices/badges/<id>/enable/
  POST /api/v1/devices/badges/<id>/revoke/
  POST /api/v1/devices/badges/<id>/destroy/
  POST /api/v1/devices/badges/<id>/archive/
  GET  /api/v1/devices/badges/<id>/history/
  GET  /api/v1/devices/badges/<id>/assignment/         (active courante)
"""
from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Badge
from .services.badges import BadgeAssignmentService
from .utils import resolve_tenant as _resolve_tenant


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════
def _get_badge(request, badge_id: str):
    tenant = _resolve_tenant(request.user)
    if tenant is None:
        return None, Response(
            {"error": "no_tenant"}, status=http_status.HTTP_403_FORBIDDEN,
        )
    try:
        badge = Badge.objects.get(pk=badge_id, tenant=tenant)
        return badge, None
    except Badge.DoesNotExist:
        return None, Response(
            {"error": "not_found"}, status=http_status.HTTP_404_NOT_FOUND,
        )


def _resolve_holder(holder_kind: str, holder_id: int | None):
    """Résout un objet titulaire selon son kind."""
    if not holder_id:
        return None
    try:
        if holder_kind == "employee":
            from employees.models import Employee
            return Employee.objects.filter(pk=holder_id).first()
        if holder_kind == "worker":
            from employees.models import Worker
            return Worker.objects.filter(pk=holder_id).first()
        if holder_kind == "visitor":
            from visitors.models import Visitor
            return Visitor.objects.filter(pk=holder_id).first()
    except Exception:
        return None
    return None


def _serialize_assignment(a) -> dict:
    """Serialize un BadgeAssignment."""
    if a is None:
        return None
    return {
        "id":             str(a.pk),
        "holder_kind":    a.holder_kind,
        "holder_label":   a.holder_label,
        "holder_id":      a.holder_object_id,
        "site_id":        a.site_id,
        "site_label":     str(a.site) if a.site else "",
        "access_level":   a.access_level,
        "assigned_at":    a.assigned_at.isoformat(),
        "activated_at":   a.activated_at.isoformat() if a.activated_at else None,
        "expires_at":     a.expires_at.isoformat() if a.expires_at else None,
        "time_window_start": a.time_window_start.isoformat() if a.time_window_start else None,
        "time_window_end":   a.time_window_end.isoformat() if a.time_window_end else None,
        "allowed_weekdays":  a.allowed_weekdays,
        "is_permanent":   a.is_permanent,
        "reason":         a.reason,
        "assigned_by":    str(a.assigned_by) if a.assigned_by else None,
        "validated_by":   str(a.validated_by) if a.validated_by else None,
        "closed_at":      a.closed_at.isoformat() if a.closed_at else None,
        "close_reason":   a.close_reason,
        "close_notes":    a.close_notes,
        "closed_by":      str(a.closed_by) if a.closed_by else None,
        "notes":          a.notes,
        "is_active":      a.is_active,
    }


# ═══════════════════════════════════════════════════════════════════
# POST /api/v1/devices/badges/<id>/assign/
# ═══════════════════════════════════════════════════════════════════
class BadgeAssignView(APIView):
    """Attribue un badge à un titulaire.

    Body attendu :
      {
        "holder_kind":    "worker" | "employee" | ...,
        "holder_id":      42,               // optionnel selon kind
        "holder_label":   "Kouassi Yao",    // fallback si pas d'objet
        "site_id":        3,
        "zone_ids":       [1, 2],           // optionnel
        "access_level":   "basic",
        "expires_at":     "2026-12-31T23:59:00Z",
        "time_window_start": "06:00",
        "time_window_end":   "22:00",
        "allowed_weekdays":  "0,1,2,3,4",   // lundi-vendredi
        "is_permanent":   false,
        "reason":         "Mission Q1 2026",
        "validated_by_id": 5,
        "notes":          "...",
      }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, badge_id):
        badge, err = _get_badge(request, badge_id)
        if err is not None:
            return err

        data = request.data or {}
        if not data.get("holder_kind"):
            return Response(
                {"error": "holder_kind_required"},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        holder_kind = data["holder_kind"]
        holder_obj = _resolve_holder(holder_kind, data.get("holder_id"))

        # Site
        site = None
        if data.get("site_id"):
            from sites.models import Site
            site = Site.objects.filter(
                pk=data["site_id"], tenant=badge.tenant,
            ).first()

        # Zones
        zones = None
        if data.get("zone_ids"):
            from sites.models import Zone
            zones = list(Zone.objects.filter(pk__in=data["zone_ids"]))

        # Validator
        validated_by = None
        if data.get("validated_by_id"):
            from django.contrib.auth import get_user_model
            validated_by = get_user_model().objects.filter(
                pk=data["validated_by_id"],
            ).first()

        result = BadgeAssignmentService.assign(
            badge=badge,
            holder_kind=holder_kind,
            holder_object=holder_obj,
            holder_label=data.get("holder_label", ""),
            site=site,
            zones=zones,
            access_level=data.get("access_level", "basic"),
            expires_at=data.get("expires_at"),
            activated_at=data.get("activated_at"),
            time_window_start=data.get("time_window_start"),
            time_window_end=data.get("time_window_end"),
            allowed_weekdays=data.get("allowed_weekdays", ""),
            is_permanent=bool(data.get("is_permanent")),
            reason=data.get("reason", ""),
            assigned_by=request.user,
            validated_by=validated_by,
            notes=data.get("notes", ""),
            metadata=data.get("metadata") or {},
        )

        if not result.ok:
            return Response({
                "error":      result.error,
                "error_code": result.error_code,
            }, status=http_status.HTTP_400_BAD_REQUEST)

        return Response({
            "ok":         True,
            "assignment": _serialize_assignment(result.assignment),
        }, status=http_status.HTTP_201_CREATED)


# ═══════════════════════════════════════════════════════════════════
# Actions cycle de vie unitaires (une classe pour éviter les duplications)
# ═══════════════════════════════════════════════════════════════════
class BadgeLifecycleActionView(APIView):
    """POST /api/v1/devices/badges/<id>/<action>/

    Actions supportées :
      unassign, suspend, resume, expire, report-lost, report-stolen,
      disable, enable, revoke, destroy, archive.

    Body optionnel : {"reason": "...", "notes": "..."}
    """
    permission_classes = [IsAuthenticated]

    ACTION_MAP = {
        "unassign":       "unassign",
        "suspend":        "suspend",
        "resume":         "resume",
        "expire":         "expire",
        "report-lost":    "report_lost",
        "report-stolen":  "report_stolen",
        "disable":        "disable",
        "enable":         "enable",
        "revoke":         "revoke",
        "destroy":        "destroy",
        "archive":        "archive",
    }

    def post(self, request, badge_id, action):
        method_name = self.ACTION_MAP.get(action)
        if method_name is None:
            return Response(
                {"error": "action_invalide",
                 "allowed": sorted(self.ACTION_MAP.keys())},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        badge, err = _get_badge(request, badge_id)
        if err is not None:
            return err

        data = request.data or {}
        reason = (data.get("reason") or "")[:240]

        method = getattr(BadgeAssignmentService, method_name)
        # unassign a signature différente
        if action == "unassign":
            result = method(
                badge=badge,
                close_reason=data.get("close_reason", "unassigned"),
                close_notes=data.get("notes", ""),
                performed_by=request.user,
            )
        else:
            result = method(
                badge=badge, reason=reason, performed_by=request.user,
            )

        if not result.ok:
            return Response({
                "error":      result.error,
                "error_code": result.error_code,
            }, status=http_status.HTTP_400_BAD_REQUEST)

        # Reload badge pour récupérer nouveau status
        badge.refresh_from_db()
        return Response({
            "ok":         True,
            "action":     action,
            "new_status": badge.status,
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/badges/<id>/history/
# ═══════════════════════════════════════════════════════════════════
class BadgeHistoryView(APIView):
    """Historique complet des assignations + événements cycle de vie."""
    permission_classes = [IsAuthenticated]

    def get(self, request, badge_id):
        badge, err = _get_badge(request, badge_id)
        if err is not None:
            return err

        assignments = BadgeAssignmentService.get_history(badge, limit=100)
        active = BadgeAssignmentService.get_active_assignment(badge)

        # Événements cycle de vie (transitions d'état)
        from devices.models_badges import BadgeLifecycleEvent
        lifecycle = BadgeLifecycleEvent.objects.filter(
            badge=badge,
        ).select_related("performed_by").order_by("-created_at")[:100]

        return Response({
            "badge": {
                "id":          str(badge.pk),
                "uid":         badge.uid,
                "type":        badge.type,
                "category":    badge.category,
                "status":      badge.status,
                "valid_from":  badge.valid_from.isoformat() if badge.valid_from else None,
                "valid_until": badge.valid_until.isoformat() if badge.valid_until else None,
                "revoked_at":  badge.revoked_at.isoformat() if badge.revoked_at else None,
                "suspended_at": badge.suspended_at.isoformat() if badge.suspended_at else None,
            },
            "active_assignment": _serialize_assignment(active),
            "assignments": [_serialize_assignment(a) for a in assignments],
            "lifecycle_events": [
                {
                    "id":           str(e.pk),
                    "from_status":  e.from_status,
                    "to_status":    e.to_status,
                    "reason":       e.reason,
                    "performed_by": str(e.performed_by) if e.performed_by else None,
                    "created_at":   e.created_at.isoformat(),
                }
                for e in lifecycle
            ],
        })


# ═══════════════════════════════════════════════════════════════════
# GET /api/v1/devices/badges/<id>/assignment/
# ═══════════════════════════════════════════════════════════════════
class BadgeCurrentAssignmentView(APIView):
    """Retourne l'assignation active courante (ou null)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, badge_id):
        badge, err = _get_badge(request, badge_id)
        if err is not None:
            return err
        active = BadgeAssignmentService.get_active_assignment(badge)
        return Response({
            "badge_id":   str(badge.pk),
            "badge_uid":  badge.uid,
            "status":     badge.status,
            "assignment": _serialize_assignment(active),
        })
