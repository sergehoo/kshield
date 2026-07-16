"""KAYDAN SHIELD — API Edge Sync (Phase 4 refonte cahier §4.5).

Endpoints agent (HMAC auth) :

    POST /api/v1/devices/edge/sync/batch/start/         (agent démarre un batch)
    POST /api/v1/devices/edge/sync/batch/<bid>/items/   (agent uploade des items)
    POST /api/v1/devices/edge/sync/batch/<bid>/complete/(agent finalise)
    POST /api/v1/devices/edge/sync/batch/<bid>/cancel/  (agent annule)
    GET  /api/v1/devices/edge/sync/batch/<bid>/status/  (agent vérifie status)

Endpoints admin (JWT auth) :

    GET  /api/v1/devices/edge/gateways/<gid>/sync/batches/  (historique)
    GET  /api/v1/devices/edge/sync/conflicts/               (liste pending)
    POST /api/v1/devices/edge/sync/conflicts/<cid>/resolve/ (résolution)
"""
from __future__ import annotations

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_hmac import AgentHmacAuthentication
from .models import LocalAgent
from .models_sync import EdgeSyncBatch, EdgeSyncConflict
from .services.sync import SyncService
from .utils import resolve_tenant as _resolve_tenant


# ═══════════════════════════════════════════════════════════════════
# Helpers de sérialisation
# ═══════════════════════════════════════════════════════════════════
def _batch_dict(batch: EdgeSyncBatch, full: bool = False) -> dict:
    d = {
        "id":               str(batch.pk),
        "batch_id":         batch.batch_id,
        "gateway_id":       str(batch.gateway_id),
        "direction":        batch.direction,
        "status":           batch.status,
        "priority":         batch.priority,
        "started_at":       batch.started_at.isoformat(),
        "processed_at":     batch.processed_at.isoformat() if batch.processed_at else None,
        "duration_ms":      batch.duration_ms,
        "items_declared":   batch.items_declared,
        "items_uploaded":   batch.items_uploaded,
        "items_processed":  batch.items_processed,
        "items_succeeded":  batch.items_succeeded,
        "items_failed":     batch.items_failed,
        "items_conflicted": batch.items_conflicted,
        "payload_size_bytes": batch.payload_size_bytes,
    }
    if full:
        d.update({
            "checksum_declared": batch.checksum_declared,
            "checksum_computed": batch.checksum_computed,
            "compression":       batch.compression,
            "encryption":        batch.encryption,
            "resume_from_offset": batch.resume_from_offset,
            "retry_count":       batch.retry_count,
            "last_error":        batch.last_error,
            "metadata":          batch.metadata,
        })
    return d


def _conflict_dict(c: EdgeSyncConflict) -> dict:
    return {
        "id":                str(c.pk),
        "batch_id":          str(c.batch_id),
        "batch_batch_id":    c.batch.batch_id if c.batch else "",
        "gateway_label":     c.batch.gateway.label if c.batch and c.batch.gateway else "",
        "entity_type":       c.entity_type,
        "entity_key":        c.entity_key,
        "edge_version":      c.edge_version,
        "cloud_version":     c.cloud_version,
        "edge_payload":      c.edge_payload,
        "cloud_payload":     c.cloud_payload,
        "resolution":        c.resolution,
        "resolution_notes":  c.resolution_notes,
        "resolved_by":       str(c.resolved_by) if c.resolved_by else None,
        "resolved_at":       c.resolved_at.isoformat() if c.resolved_at else None,
        "created_at":        c.created_at.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# Endpoints AGENT (HMAC)
# ═══════════════════════════════════════════════════════════════════
class AgentSyncStartView(APIView):
    """POST /edge/sync/batch/start/

    Body attendu :
      {
        "batch_id":         "uuid-timestamp-hash",
        "direction":        "upload" | "download",
        "priority":         "low|normal|high|critical",
        "items_declared":   42,
        "checksum_declared": "sha256:...",
        "compression":      "gzip" | "",
        "metadata":         {...}
      }
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request):
        agent = getattr(request, "agent", None)
        if agent is None or agent.revoked_at:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)

        data = request.data or {}
        result = SyncService.start_batch(
            gateway=agent,
            batch_id=data.get("batch_id", ""),
            direction=data.get("direction", "upload"),
            items_declared=int(data.get("items_declared", 0) or 0),
            priority=data.get("priority", "normal"),
            checksum_declared=data.get("checksum_declared", ""),
            compression=data.get("compression", ""),
            metadata=data.get("metadata") or {},
        )
        if not result.ok:
            return Response(
                {"error": result.error, "code": result.error_code},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return Response({"ok": True, "batch": _batch_dict(result.batch)},
                          status=http_status.HTTP_201_CREATED)


class AgentSyncItemsView(APIView):
    """POST /edge/sync/batch/<bid>/items/

    Body : {"items": [{"entity_type": "event", "entity_key": "uuid", "payload": {...}}, ...]}
    Max 500 items par requête (chunk).
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request, bid):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)

        try:
            batch = EdgeSyncBatch.objects.get(batch_id=bid, gateway=agent)
        except EdgeSyncBatch.DoesNotExist:
            return Response({"error": "batch_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        if batch.status not in ("uploading", "pending"):
            return Response({"error": "batch_not_uploading",
                              "status": batch.status},
                              status=http_status.HTTP_400_BAD_REQUEST)

        items = (request.data or {}).get("items") or []
        if not isinstance(items, list):
            return Response({"error": "items_must_be_list"},
                              status=http_status.HTTP_400_BAD_REQUEST)
        if len(items) > 500:
            return Response(
                {"error": "chunk_too_big", "max": 500, "got": len(items)},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        stats = SyncService.add_items(batch, items)
        return Response({"ok": True, "stats": stats})


class AgentSyncCompleteView(APIView):
    """POST /edge/sync/batch/<bid>/complete/

    Body : {"checksum_computed": "sha256:..."}
    """
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request, bid):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)

        try:
            batch = EdgeSyncBatch.objects.get(batch_id=bid, gateway=agent)
        except EdgeSyncBatch.DoesNotExist:
            return Response({"error": "batch_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        result = SyncService.complete_batch(
            batch=batch,
            checksum_computed=(request.data or {}).get("checksum_computed", ""),
        )
        return Response({"ok": result.ok, "batch": _batch_dict(result.batch, full=True)})


class AgentSyncCancelView(APIView):
    """POST /edge/sync/batch/<bid>/cancel/"""
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def post(self, request, bid):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            batch = EdgeSyncBatch.objects.get(batch_id=bid, gateway=agent)
        except EdgeSyncBatch.DoesNotExist:
            return Response({"error": "batch_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        reason = (request.data or {}).get("reason", "")
        SyncService.cancel_batch(batch, reason=reason)
        return Response({"ok": True, "status": "cancelled"})


class AgentSyncStatusView(APIView):
    """GET /edge/sync/batch/<bid>/status/"""
    permission_classes = []
    authentication_classes = [AgentHmacAuthentication]

    def get(self, request, bid):
        agent = getattr(request, "agent", None)
        if agent is None:
            return Response({"error": "unauthorized"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            batch = EdgeSyncBatch.objects.get(batch_id=bid, gateway=agent)
        except EdgeSyncBatch.DoesNotExist:
            return Response({"error": "batch_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)
        return Response(_batch_dict(batch, full=True))


# ═══════════════════════════════════════════════════════════════════
# Endpoints ADMIN (JWT)
# ═══════════════════════════════════════════════════════════════════
class SyncBatchesListView(APIView):
    """GET /edge/gateways/<gid>/sync/batches/  — historique."""
    permission_classes = [IsAuthenticated]

    def get(self, request, gid):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            gateway = LocalAgent.objects.get(pk=gid, tenant=tenant)
        except LocalAgent.DoesNotExist:
            return Response({"error": "gateway_not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        # Filtres optionnels
        limit = min(int(request.query_params.get("limit", 50)), 500)
        qs = EdgeSyncBatch.objects.filter(gateway=gateway)
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        direction = request.query_params.get("direction")
        if direction:
            qs = qs.filter(direction=direction)

        total = qs.count()
        batches = qs.order_by("-started_at")[:limit]

        return Response({
            "count":   total,
            "results": [_batch_dict(b) for b in batches],
        })


class SyncConflictsListView(APIView):
    """GET /edge/sync/conflicts/  — conflits en attente pour ce tenant."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"count": 0, "results": []})

        resolution = request.query_params.get("resolution", "pending")
        limit = min(int(request.query_params.get("limit", 100)), 500)

        qs = EdgeSyncConflict.objects.filter(tenant=tenant)
        if resolution:
            qs = qs.filter(resolution=resolution)
        total = qs.count()
        conflicts = qs.select_related(
            "batch", "batch__gateway", "item",
        ).order_by("-created_at")[:limit]

        return Response({
            "count":   total,
            "results": [_conflict_dict(c) for c in conflicts],
        })


class SyncConflictResolveView(APIView):
    """POST /edge/sync/conflicts/<cid>/resolve/

    Body : {"resolution": "cloud_wins|edge_wins|merge|ignore|escalated",
             "notes": "..."}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, cid):
        tenant = _resolve_tenant(request.user)
        if tenant is None:
            return Response({"error": "no_tenant"},
                              status=http_status.HTTP_403_FORBIDDEN)
        try:
            conflict = EdgeSyncConflict.objects.get(pk=cid, tenant=tenant)
        except EdgeSyncConflict.DoesNotExist:
            return Response({"error": "not_found"},
                              status=http_status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        resolution = data.get("resolution", "")
        notes = data.get("notes", "")

        result = SyncService.resolve_conflict(
            conflict=conflict, resolution=resolution,
            user=request.user, notes=notes,
        )
        if not result.ok:
            return Response(
                {"error": result.error, "code": result.error_code},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        conflict.refresh_from_db()
        return Response({"ok": True, "conflict": _conflict_dict(conflict)})
