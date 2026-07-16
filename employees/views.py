import base64
import logging

from django.conf import settings as django_settings
from django.core.files.base import ContentFile
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Department, Employee, EmployeeAuthorization, EmployeeContract,
    EmployeeSchedule, FaceProfile, JobPosition,
)
from .serializers import (
    DepartmentSerializer, EmployeeAuthorizationSerializer, EmployeeContractSerializer,
    EmployeeScheduleSerializer, EmployeeSerializer, JobPositionSerializer,
)
from core.tenant_mixins import TenantScopedViewSetMixin

logger = logging.getLogger(__name__)


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("company", "parent").all()
    serializer_class = DepartmentSerializer
    search_fields = ("name", "code")
    filterset_fields = ("company", "parent")


class JobPositionViewSet(viewsets.ModelViewSet):
    queryset = JobPosition.objects.all()
    serializer_class = JobPositionSerializer
    search_fields = ("title", "code")
    filterset_fields = ("company",)


@extend_schema_view(
    list=extend_schema(tags=["Employes"], summary="Liste des employés KAYDAN",
        description="Filtrer par filiale, département, statut, type de contrat. "
                    "Recherche sur matricule / nom / email / téléphone."),
    create=extend_schema(tags=["Employes"], summary="Créer un employé"),
    retrieve=extend_schema(tags=["Employes"], summary="Détail employé"),
    update=extend_schema(tags=["Employes"]),
    partial_update=extend_schema(tags=["Employes"]),
    destroy=extend_schema(tags=["Employes"]),
)
class EmployeeViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """Annuaire RH des collaborateurs KAYDAN porteurs de badge NFC."""
    queryset = Employee.objects.select_related(
        "tenant", "company", "department", "position", "manager",
    ).prefetch_related("authorized_sites").all()
    serializer_class = EmployeeSerializer
    search_fields = ("matricule", "first_name", "last_name", "email", "phone")
    filterset_fields = ("tenant", "company", "department", "status", "contract_type")

    def get_queryset(self):
        # RBAC multi-filiale : restreint aux filiales du user (sauf super-admin)
        from accounts.scoping import scope_queryset_by_company
        return scope_queryset_by_company(super().get_queryset(), self.request.user, "company")

    # tenant auto-injecté par TenantScopedViewSetMixin (voir base class ci-dessus).

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        emp = self.get_object()
        emp.status = "terminated"
        emp.save(update_fields=["status"])
        return Response({"status": emp.status})


class EmployeeContractViewSet(viewsets.ModelViewSet):
    queryset = EmployeeContract.objects.select_related("employee").all()
    serializer_class = EmployeeContractSerializer
    filterset_fields = ("employee", "contract_type")


class EmployeeAuthorizationViewSet(viewsets.ModelViewSet):
    queryset = EmployeeAuthorization.objects.select_related("employee", "zone").all()
    serializer_class = EmployeeAuthorizationSerializer
    filterset_fields = ("employee", "zone")


class EmployeeScheduleViewSet(viewsets.ModelViewSet):
    queryset = EmployeeSchedule.objects.select_related("employee").all()
    serializer_class = EmployeeScheduleSerializer
    filterset_fields = ("employee", "day_of_week", "shift")


# ===========================================================================
# Reconnaissance faciale — Enroll / Match (consommé par templates/face_test.html)
# ===========================================================================
def _decode_b64_image(data_url: str):
    """Décode un data:image/jpeg;base64,... en bytes + extension."""
    if not data_url:
        return None, None
    if "," in data_url:
        header, payload = data_url.split(",", 1)
    else:
        header, payload = "", data_url
    try:
        raw = base64.b64decode(payload)
    except Exception:
        return None, None
    ext = "jpg"
    if "image/png" in header:
        ext = "png"
    elif "image/webp" in header:
        ext = "webp"
    return raw, ext


def _cosine_similarity(a: list, b: list) -> float:
    """Similarité cosinus entre deux embeddings (1.0 = identique, 0 = orthogonal)."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _save_source_image(profile: FaceProfile, source_b64: str, employee: Employee) -> None:
    """Persist une capture base64 sur le FaceProfile (best-effort)."""
    raw, ext = _decode_b64_image(source_b64)
    if raw:
        fname = f"{employee.matricule or employee.pk}_{int(timezone.now().timestamp())}.{ext}"
        profile.source_image.save(fname, ContentFile(raw), save=False)


def _compute_server_side(source_b64: str) -> dict:
    """Pipeline InsightFace : décode → détecte → extrait embedding 512D + qualité.

    Renvoie le dict retourné par ``FaceEngine.compute_embedding``.
    Lève ``FaceEngineUnavailable`` (503) ou ``FaceEngineError`` (400).
    """
    from .face_engine import get_engine
    return get_engine().compute_embedding(source_b64)


@extend_schema_view(
    post=extend_schema(
        tags=["Employes"],
        summary="Enrôler un visage employé (face-api.js OU InsightFace)",
        description=(
            "Deux modes d'enrôlement supportés :\n\n"
            "1. **Client-side (face-api.js, 128D)** : fournir ``embedding`` calculé "
            "navigateur + ``source_image`` (optionnel). Rapide, RGPD-friendly.\n"
            "2. **Server-side (InsightFace, 512D)** : fournir uniquement "
            "``source_image`` + ``engine=\"insightface\"``. Le serveur calcule "
            "l'embedding 512D ArcFace sur GPU. Précision supérieure, indispensable "
            "pour les checkpoints production.\n\n"
            "Désactive tous les anciens profils actifs du même employé."
        ),
    ),
)
class FaceEnrollAPIView(APIView):
    """POST /api/v1/employees/face/enroll/ — enregistre un profil facial."""

    def post(self, request):
        from .face_engine import FaceEngineError, FaceEngineUnavailable

        employee_id = request.data.get("employee_id")
        embedding = request.data.get("embedding")
        quality = float(request.data.get("quality") or 0.0)
        source_b64 = request.data.get("source_image")
        engine = (request.data.get("engine") or "client").lower()
        model = request.data.get("model") or "facenet_v1"

        if not employee_id:
            return Response({"error": "employee_id manquant."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"error": f"Employé #{employee_id} introuvable."},
                            status=status.HTTP_404_NOT_FOUND)

        # ── Mode SERVER (InsightFace + liveness) ─────────────────────
        engine_meta = None
        if engine == "insightface":
            if not source_b64:
                return Response(
                    {"error": "source_image requis en mode engine=insightface."},
                    status=status.HTTP_400_BAD_REQUEST)
            try:
                res = _compute_server_side(source_b64)
            except FaceEngineUnavailable as exc:
                return Response({"error": str(exc), "engine": "insightface"},
                                status=status.HTTP_503_SERVICE_UNAVAILABLE)
            except FaceEngineError as exc:
                return Response({"error": str(exc), "engine": "insightface"},
                                status=status.HTTP_400_BAD_REQUEST)

            # ── Anti-spoofing : bloque l'enrôlement si spoof détecté ──
            face_cfg = django_settings.KAYDAN_SHIELD["FACE"]
            block_on_spoof = bool(face_cfg.get("LIVENESS", {}).get("BLOCK_ENROLL_ON_SPOOF", True))
            liveness = res.get("liveness") or {}
            if (block_on_spoof and liveness.get("available") is not False
                    and liveness.get("is_live") is False):
                return Response({
                    "error": "Visage potentiellement falsifié (photo/écran/masque) — "
                             "enrôlement refusé.",
                    "engine": "insightface",
                    "liveness": liveness,
                    "bbox": res.get("bbox"),
                }, status=status.HTTP_403_FORBIDDEN)

            embedding = res["embedding"]
            quality = res["quality"]
            model = "insightface"
            engine_meta = {
                "provider": res.get("provider"),
                "det_score": res.get("det_score"),
                "pose": res.get("pose"),
                "faces_detected": res.get("faces_detected"),
                "bbox": res.get("bbox"),
                "liveness": liveness,
            }

        # ── Mode CLIENT (face-api.js, embedding fourni) ──────────────
        else:
            if not isinstance(embedding, list) or len(embedding) < 64:
                return Response(
                    {"error": "embedding invalide (>=64 floats) ou engine=insightface manquant."},
                    status=status.HTTP_400_BAD_REQUEST)

        # ── Persistance ──────────────────────────────────────────────
        FaceProfile.objects.filter(employee=employee, is_active=True).update(is_active=False)

        profile = FaceProfile(
            employee=employee,
            embedding=embedding,
            embedding_model=model,
            embedding_dim=len(embedding),
            quality_score=max(0.0, min(1.0, quality)),
            is_active=True,
        )
        if source_b64:
            _save_source_image(profile, source_b64, employee)
        profile.save()

        payload = {
            "ok": True,
            "profile_id": profile.pk,
            "engine": engine,
            "employee": {
                "id": employee.pk,
                "matricule": employee.matricule,
                "name": f"{employee.first_name} {employee.last_name}".strip(),
            },
            "embedding_dim": profile.embedding_dim,
            "quality": profile.quality_score,
            "enrolled_at": profile.enrolled_at.isoformat(),
        }
        if engine_meta:
            payload["engine_meta"] = engine_meta
        return Response(payload, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
        tags=["Employes"],
        summary="Identifier un visage (face-api.js OU InsightFace)",
        description=(
            "Deux modes de match :\n\n"
            "1. **Client-side** : fournir ``embedding`` (128D ou 512D).\n"
            "2. **Server-side** : fournir ``source_image`` + ``engine=\"insightface\"``, "
            "le serveur calcule l'embedding 512D puis compare.\n\n"
            "Le serveur filtre les FaceProfile par ``embedding_dim`` égale à celle "
            "de la requête pour ne comparer que des vecteurs compatibles."
        ),
    ),
)
class FaceMatchAPIView(APIView):
    """POST /api/v1/employees/face/match/ — identifie un visage."""

    def post(self, request):
        from .face_engine import FaceEngineError, FaceEngineUnavailable

        embedding = request.data.get("embedding")
        source_b64 = request.data.get("source_image")
        engine = (request.data.get("engine") or "client").lower()
        threshold = float(request.data.get("threshold") or 0.55)

        engine_meta = None
        if engine == "insightface":
            if not source_b64:
                return Response(
                    {"error": "source_image requis en mode engine=insightface."},
                    status=status.HTTP_400_BAD_REQUEST)
            try:
                res = _compute_server_side(source_b64)
            except FaceEngineUnavailable as exc:
                return Response({"error": str(exc), "engine": "insightface"},
                                status=status.HTTP_503_SERVICE_UNAVAILABLE)
            except FaceEngineError as exc:
                return Response({"error": str(exc), "engine": "insightface"},
                                status=status.HTTP_400_BAD_REQUEST)
            embedding = res["embedding"]
            engine_meta = {
                "provider": res.get("provider"),
                "det_score": res.get("det_score"),
                "pose": res.get("pose"),
                "quality": res.get("quality"),
                "bbox": res.get("bbox"),
                "liveness": res.get("liveness"),
            }
        elif not isinstance(embedding, list) or len(embedding) < 64:
            return Response({"error": "embedding invalide."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Plancher dur de sécurité (cf. FaceProfile.threshold docstring)
        threshold = max(0.50, min(0.95, threshold))

        best, best_score = None, -1.0
        top3 = []
        # On ne compare qu'aux profils de même dimension (un 512D ne se compare
        # pas à un 128D — ni mathématiquement ni sémantiquement).
        for profile in FaceProfile.objects.filter(
            is_active=True, embedding_dim=len(embedding),
        ).select_related("employee", "employee__company"):
            try:
                score = _cosine_similarity(embedding, profile.embedding)
            except Exception:
                logger.debug("Cosine échoué pour profil %s", profile.pk, exc_info=True)
                continue
            top3.append((score, profile))
            if score > best_score:
                best, best_score = profile, score

        top3.sort(key=lambda t: t[0], reverse=True)
        top3 = top3[:3]
        candidates_total = FaceProfile.objects.filter(
            is_active=True, embedding_dim=len(embedding),
        ).count()

        payload = {
            "engine": engine,
            "embedding_dim": len(embedding),
            "threshold": threshold,
            "candidates_compared": candidates_total,
            "top3": [{
                "employee_id": p.employee.pk,
                "name": f"{p.employee.first_name} {p.employee.last_name}".strip(),
                "matricule": p.employee.matricule,
                "score": round(s, 4),
            } for s, p in top3],
        }
        if engine_meta:
            payload["engine_meta"] = engine_meta

        if not best or best_score < threshold:
            payload["matched"] = False
            payload["best_score"] = round(best_score, 4) if best else None
            return Response(payload)

        best.last_matched_at = timezone.now()
        best.match_count += 1
        best.save(update_fields=["last_matched_at", "match_count"])

        emp = best.employee
        payload.update({
            "matched": True,
            "score": round(best_score, 4),
            "employee": {
                "id": emp.pk,
                "matricule": emp.matricule,
                "name": f"{emp.first_name} {emp.last_name}".strip(),
                "company": emp.company.name if emp.company else None,
                "department": emp.department.name if emp.department else None,
                "status": emp.status,
            },
            "profile_id": best.pk,
            "match_count": best.match_count,
        })
        return Response(payload)


class FaceEngineStatusAPIView(APIView):
    """GET /api/v1/employees/face/status/ — état du moteur InsightFace.

    Utilisé par la page admin pour afficher si le pipeline serveur est dispo,
    quel provider ONNX a été retenu, et le modèle utilisé. Ne déclenche pas
    le warm-up (lazy init reste différé au premier appel enroll/match).
    """

    def get(self, request):
        try:
            from .face_engine import get_engine
            return Response(get_engine().status())
        except Exception as exc:
            logger.warning("FaceEngineStatus indisponible : %s", exc, exc_info=True)
            return Response({
                "enabled": False, "ready": False, "error": str(exc),
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
