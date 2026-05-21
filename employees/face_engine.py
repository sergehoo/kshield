"""KAYDAN SHIELD — Moteur de reconnaissance faciale InsightFace (GPU).

Wrap autour d'``insightface.app.FaceAnalysis`` qui charge le pack ``buffalo_l``
(détecteur RetinaFace + ArcFace IResNet100 512D + landmarks 106pt).

**Architecture** :
- Singleton thread-safe → l'objet ``FaceAnalysis`` (~280 Mo en VRAM) est instancié
  une seule fois par worker process. Le premier appel est lent (1-3s de prepare),
  ensuite chaque embedding prend 15-40 ms sur GPU, 200-500 ms sur CPU.
- Providers ONNX configurables → ``CUDAExecutionProvider`` en priorité, fallback
  CPU automatique si CUDA n'est pas dispo (utile en dev sur macOS).
- Lazy load → ``django.apps.AppConfig.ready()`` n'est PAS un bon endroit pour
  l'init (pourrait bloquer le boot). On l'instancie au premier appel API.
- Désactivable via ``settings.KAYDAN_SHIELD["FACE"]["ENABLED"] = False`` :
  les endpoints renvoient 503, la page admin retombe sur face-api.js client-only.

**Métriques exposées** (cf. ``compute_embedding`` docstring) :
- ``embedding``    : list[float] de dim 512 (cosine-comparable, norme 1.0 ~ après normalize)
- ``det_score``    : 0–1, qualité de la détection RetinaFace
- ``bbox``         : [x1, y1, x2, y2] dans le repère image
- ``pose``         : {yaw, pitch, roll} en degrés (utile pour rejeter les visages trop inclinés)
- ``age``, ``gender`` : estimations (optionnelles, fournies par buffalo_l)
- ``quality``      : score composite 0–1 calculé à partir de det_score + pose
"""
from __future__ import annotations

import base64
import logging
import threading
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class FaceEngineError(RuntimeError):
    """Exception levée pour toute erreur métier du moteur (modèle, dépendances, image)."""


class FaceEngineUnavailable(FaceEngineError):
    """Le moteur est désactivé via settings ou les deps ne sont pas installées."""


# ---------------------------------------------------------------------------
# Singleton thread-safe
# ---------------------------------------------------------------------------
_engine_lock = threading.Lock()
_engine_instance: Optional["FaceEngine"] = None


def get_engine() -> "FaceEngine":
    """Retourne le singleton FaceEngine (init lazy au premier appel)."""
    global _engine_instance
    if _engine_instance is not None:
        return _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = FaceEngine()
        return _engine_instance


# ---------------------------------------------------------------------------
# Moteur
# ---------------------------------------------------------------------------
class FaceEngine:
    """Wrapper InsightFace : init lazy, embedding + quality metrics."""

    def __init__(self):
        self._cfg = settings.KAYDAN_SHIELD["FACE"]
        self._app: Optional[Any] = None  # insightface.app.FaceAnalysis
        self._ready = False
        self._provider_used: Optional[str] = None

    # ------------------------------------------------------------------
    # Init paresseuse — appelée au premier compute_embedding/extract.
    # ------------------------------------------------------------------
    def _ensure_ready(self) -> None:
        if self._ready:
            return
        if not self._cfg.get("ENABLED", True):
            raise FaceEngineUnavailable(
                "Moteur de reconnaissance faciale désactivé (FACE_ENGINE_ENABLED=False)."
            )
        try:
            import insightface  # noqa: F401
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise FaceEngineUnavailable(
                "Dépendances InsightFace manquantes. Installer : "
                "`pip install insightface onnxruntime-gpu opencv-python-headless`."
            ) from exc

        providers = self._cfg.get("PROVIDERS") or [
            "CUDAExecutionProvider", "CPUExecutionProvider",
        ]
        model_name = self._cfg.get("MODEL_NAME", "buffalo_l")
        ctx_id = int(self._cfg.get("CTX_ID", 0))
        det_size = int(self._cfg.get("DET_SIZE", 640))
        model_root = self._cfg.get("MODEL_ROOT") or None

        logger.info(
            "InsightFace init : model=%s providers=%s ctx_id=%s det_size=%s",
            model_name, providers, ctx_id, det_size,
        )

        kwargs: dict[str, Any] = {"name": model_name, "providers": providers}
        if model_root:
            kwargs["root"] = model_root

        try:
            app = FaceAnalysis(**kwargs)
            app.prepare(ctx_id=ctx_id, det_size=(det_size, det_size))
        except Exception as exc:
            # Si CUDA explose, on retente en CPU pour ne pas tuer le service entier.
            if any("CUDA" in p for p in providers):
                logger.warning(
                    "Init CUDA échouée (%s), fallback CPU automatique.", exc,
                )
                try:
                    app = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
                    app.prepare(ctx_id=-1, det_size=(det_size, det_size))
                    self._provider_used = "CPUExecutionProvider"
                except Exception as exc2:  # pragma: no cover
                    raise FaceEngineError(
                        f"Init InsightFace impossible (GPU + CPU ont échoué) : {exc2}"
                    ) from exc2
            else:
                raise FaceEngineError(f"Init InsightFace échouée : {exc}") from exc
        else:
            # On ne sait pas exactement quel provider a été retenu par ORT ;
            # on garde le premier candidat comme indication.
            self._provider_used = providers[0] if providers else "unknown"

        self._app = app
        self._ready = True
        logger.info("InsightFace prêt (provider=%s).", self._provider_used)

    # ------------------------------------------------------------------
    # Décodage image (base64 ou bytes bruts) → ndarray BGR pour InsightFace.
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_image(payload):
        """Accepte data URL (``data:image/...;base64,...``), base64 nu, ou bytes.

        Retourne un ``numpy.ndarray`` HxWx3 en BGR (convention OpenCV) ou lève
        ``FaceEngineError`` si le format est invalide.
        """
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FaceEngineUnavailable(
                "OpenCV/NumPy manquants (`pip install opencv-python-headless numpy`)."
            ) from exc

        if isinstance(payload, str):
            if "," in payload and payload.startswith("data:"):
                payload = payload.split(",", 1)[1]
            try:
                raw = base64.b64decode(payload)
            except Exception as exc:
                raise FaceEngineError(f"Image base64 invalide : {exc}") from exc
        elif isinstance(payload, (bytes, bytearray, memoryview)):
            raw = bytes(payload)
        else:
            raise FaceEngineError("Type d'image non supporté (attendu : str base64 ou bytes).")

        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise FaceEngineError("Image illisible (format non supporté ou corrompu).")
        return img

    # ------------------------------------------------------------------
    # Compute embedding 512D + quality metrics + liveness
    # ------------------------------------------------------------------
    def compute_embedding(self, image_payload, pick: str = "largest",
                          run_liveness: bool = True) -> dict:
        """Détecte le visage, calcule l'embedding 512D + métriques de qualité.

        Args:
            image_payload: image source (data URL base64 OU bytes JPEG/PNG).
            pick: stratégie si plusieurs visages détectés :
                ``"largest"`` (défaut, le plus grand bbox), ``"center"``
                (le plus proche du centre), ``"first"`` (premier renvoyé par RetinaFace).

        Returns:
            dict avec clés :
              - ``embedding`` (list[float], 512D, normalisé)
              - ``embedding_dim`` (int, 512)
              - ``model`` (str, "insightface")
              - ``det_score`` (float, 0–1)
              - ``bbox`` (list[int], [x1, y1, x2, y2])
              - ``pose`` (dict yaw/pitch/roll en degrés, ou None)
              - ``age`` (int|None)
              - ``gender`` (str|None : "M"/"F")
              - ``quality`` (float composite 0–1)
              - ``faces_detected`` (int)
              - ``provider`` (str, provider ONNX utilisé)

        Raises:
            FaceEngineError si aucun visage détecté ou si l'image est invalide.
            FaceEngineUnavailable si les deps ne sont pas installées / engine off.
        """
        self._ensure_ready()
        img = self._decode_image(image_payload)
        faces = self._app.get(img)
        if not faces:
            raise FaceEngineError(
                "Aucun visage détecté dans l'image (essayer un meilleur cadrage)."
            )

        # Sélection du visage de référence
        if pick == "largest":
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        elif pick == "center":
            h, w = img.shape[:2]
            cx, cy = w / 2, h / 2
            face = min(faces, key=lambda f: (
                ((f.bbox[0] + f.bbox[2]) / 2 - cx) ** 2 +
                ((f.bbox[1] + f.bbox[3]) / 2 - cy) ** 2
            ))
        else:
            face = faces[0]

        # Embedding 512D : on utilise normed_embedding (norme 1.0, ratio cosinus = dot)
        emb = getattr(face, "normed_embedding", None)
        if emb is None:
            emb = face.embedding  # fallback non normalisé
        embedding = [float(x) for x in emb.tolist()]

        # Pose (degrés) — fourni par buffalo_l via le module 3D landmark
        pose_attr = getattr(face, "pose", None)
        pose = None
        if pose_attr is not None and len(pose_attr) >= 3:
            pose = {
                "pitch": float(pose_attr[0]),
                "yaw":   float(pose_attr[1]),
                "roll":  float(pose_attr[2]),
            }

        # Score qualité composite : combine det_score et pénalisation pose.
        det_score = float(getattr(face, "det_score", 0.0) or 0.0)
        quality = self._compute_quality(det_score, pose)

        # Sexe/âge optionnels
        sex_idx = getattr(face, "sex", None)
        gender = None
        if sex_idx is not None:
            gender = "F" if sex_idx == "F" or sex_idx == 0 else "M"
        age = getattr(face, "age", None)
        if age is not None:
            try:
                age = int(age)
            except (TypeError, ValueError):
                age = None

        bbox = [int(v) for v in face.bbox.tolist()]

        result = {
            "embedding": embedding,
            "embedding_dim": len(embedding),
            "model": "insightface",
            "det_score": det_score,
            "bbox": bbox,
            "pose": pose,
            "age": age,
            "gender": gender,
            "quality": quality,
            "faces_detected": len(faces),
            "provider": self._provider_used or "unknown",
            "liveness": None,
        }

        # ── Anti-spoofing (SilentFace / MiniFASNet) ──────────────────
        # On l'exécute par défaut mais on n'échoue pas si les modèles
        # ne sont pas dispos — la décision finale (block/accept) revient
        # à la couche API (cf. FaceEnrollAPIView / FaceMatchAPIView).
        if run_liveness:
            try:
                from .antispoof import get_detector, LivenessUnavailable
                result["liveness"] = get_detector().check(img, bbox)
            except LivenessUnavailable as exc:
                # Pas de modèles → on signale juste, sans planter
                result["liveness"] = {
                    "is_live": None,
                    "available": False,
                    "reason": str(exc),
                }
            except Exception as exc:
                logger.warning("Liveness check a échoué : %s", exc, exc_info=True)
                result["liveness"] = {
                    "is_live": None,
                    "available": False,
                    "reason": f"Erreur inférence : {exc}",
                }

        return result

    # ------------------------------------------------------------------
    # Quality scoring composite
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_quality(det_score: float, pose: Optional[dict]) -> float:
        """Score qualité 0–1 = det_score · pénalité_pose.

        Pénalise un visage trop incliné : 30° = pénalité 0.7, 45° = 0.3, 60° = 0.
        """
        if det_score < 0.3:
            return 0.0
        base = max(0.0, min(1.0, det_score))
        if not pose:
            return base
        # max(|yaw|, |pitch|, |roll|) → angle d'inclinaison "pire axe"
        max_angle = max(
            abs(pose.get("yaw", 0.0)),
            abs(pose.get("pitch", 0.0)),
            abs(pose.get("roll", 0.0)),
        )
        # Au-delà de 60° on considère inutilisable
        pose_penalty = max(0.0, 1.0 - (max_angle / 60.0))
        return round(base * pose_penalty, 4)

    # ------------------------------------------------------------------
    # Métadonnées d'état (utilisées par /api/v1/employees/face/status/)
    # ------------------------------------------------------------------
    def status(self) -> dict:
        """Retourne un état complet du moteur (sans déclencher le warm-up)."""
        out = {
            "enabled":   bool(self._cfg.get("ENABLED", True)),
            "ready":     self._ready,
            "model":     self._cfg.get("MODEL_NAME", "buffalo_s"),
            "ctx_id":    int(self._cfg.get("CTX_ID", -1)),
            "providers": list(self._cfg.get("PROVIDERS") or []),
            "provider_used": self._provider_used,
            "det_size":  int(self._cfg.get("DET_SIZE", 640)),
            "match_threshold": float(self._cfg.get("MATCH_THRESHOLD", 0.60)),
            "min_det_score":   float(self._cfg.get("MIN_DET_SCORE", 0.55)),
        }
        # Statut liveness (sans déclencher le load des modèles MiniFASNet)
        try:
            from .antispoof import get_detector
            out["liveness"] = get_detector().status()
        except Exception as exc:
            out["liveness"] = {"enabled": False, "ready": False, "error": str(exc)}
        return out
