"""KAYDAN SHIELD — moteur de reconnaissance faciale YOLOv8 + ArcFace.

Architecture :
- **Détection** : YOLOv8-face (yolov8n-face.pt par défaut, ou yolov8s/m/l selon
  config). Plus précis qu'InsightFace RetinaFace en conditions difficiles :
  visages de profil, occlusions partielles, foule, basse lumière.
- **Embedding** : ArcFace 512D via InsightFace.model_zoo. Même format que
  l'ancien backend → les embeddings existants en base restent compatibles
  (cosine similarity entre les deux est OK car même modèle ArcFace).

Activation : ``settings.KAYDAN_SHIELD["FACE"]["BACKEND"] = "yolov8"``

Dépendances :
    pip install ultralytics>=8.0 insightface opencv-python-headless

Le poids YOLOv8-face est téléchargé automatiquement depuis HuggingFace ou
le fichier local pointé par ``FACE_YOLO_WEIGHTS``.
"""
from __future__ import annotations

import base64
import logging
import os
import threading
from typing import Any, Optional

from django.conf import settings

from .face_engine import FaceEngineError, FaceEngineUnavailable

logger = logging.getLogger(__name__)


#: URL HF par défaut pour les poids yolov8n-face (modèle nano, 6 MB).
_DEFAULT_YOLO_WEIGHTS_URL = (
    "https://github.com/derronqi/yolov8-face/releases/download/"
    "v0.0.0/yolov8n-face.pt"
)


class YoloV8FaceEngine:
    """Backend YOLOv8 pour la détection + ArcFace pour l'embedding.

    Interface identique à ``employees.face_engine.FaceEngine`` :
    - ``compute_embedding(image, pick="largest", run_liveness=True)`` → dict
    """

    _LOCK = threading.Lock()
    _INSTANCE: Optional["YoloV8FaceEngine"] = None

    @classmethod
    def get_instance(cls) -> "YoloV8FaceEngine":
        with cls._LOCK:
            if cls._INSTANCE is None:
                cls._INSTANCE = cls()
            return cls._INSTANCE

    def __init__(self):
        self._cfg = settings.KAYDAN_SHIELD["FACE"]
        self._yolo = None        # ultralytics.YOLO
        self._rec_model = None   # insightface.model_zoo recognition
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
                "Moteur de reconnaissance faciale désactivé."
            )

        # ── 1) Charger YOLOv8 pour détection ──
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise FaceEngineUnavailable(
                "Module 'ultralytics' manquant. Installer : "
                "`pip install ultralytics>=8.0`."
            ) from exc

        weights = (self._cfg.get("YOLO_WEIGHTS")
                   or os.environ.get("FACE_YOLO_WEIGHTS")
                   or "yolov8n-face.pt")
        if not os.path.exists(weights):
            # Si pas dispo localement, ultralytics téléchargera automatiquement.
            # Mais yolov8n-face n'est pas dans le hub officiel — fallback HF.
            from urllib.request import urlretrieve
            target_dir = self._cfg.get("MODEL_ROOT") or os.path.expanduser(
                "~/.kaydan/face_weights"
            )
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, "yolov8n-face.pt")
            if not os.path.exists(target_path):
                logger.info("Téléchargement yolov8n-face → %s", target_path)
                try:
                    urlretrieve(_DEFAULT_YOLO_WEIGHTS_URL, target_path)
                except Exception as exc:
                    raise FaceEngineUnavailable(
                        f"Impossible de télécharger {_DEFAULT_YOLO_WEIGHTS_URL} : {exc}. "
                        "Téléchargez manuellement le fichier et pointez "
                        "FACE_YOLO_WEIGHTS dessus."
                    ) from exc
            weights = target_path

        logger.info("Init YOLOv8 face detector : weights=%s", weights)
        self._yolo = YOLO(weights)

        # ── 2) Charger ArcFace pour l'embedding ──
        try:
            from insightface.model_zoo import get_model
        except ImportError as exc:
            raise FaceEngineUnavailable(
                "Module 'insightface' manquant pour l'embedding ArcFace. "
                "Installer : `pip install insightface`."
            ) from exc

        providers = self._cfg.get("PROVIDERS") or [
            "CUDAExecutionProvider", "CPUExecutionProvider",
        ]
        rec_name = self._cfg.get("ARCFACE_MODEL") or "buffalo_l"
        # On utilise le recognition module standalone d'InsightFace
        try:
            rec = get_model("buffalo_l", providers=providers)
            rec.prepare(ctx_id=int(self._cfg.get("CTX_ID", -1)))
        except Exception:
            # Fallback : utilise FaceAnalysis(name=buffalo_l, recognition only)
            try:
                from insightface.app import FaceAnalysis
                rec = FaceAnalysis(
                    name=rec_name,
                    providers=providers,
                    allowed_modules=["recognition"],
                )
                rec.prepare(
                    ctx_id=int(self._cfg.get("CTX_ID", -1)),
                    det_size=(640, 640),
                )
                self._rec_via_analysis = True
            except Exception as exc:
                raise FaceEngineError(
                    f"Init ArcFace embedding échouée : {exc}"
                ) from exc
        else:
            self._rec_via_analysis = False
        self._rec_model = rec
        self._provider_used = providers[0] if providers else "unknown"
        self._ready = True
        logger.info("YoloV8FaceEngine prêt (rec_provider=%s).", self._provider_used)

    # ------------------------------------------------------------------
    # Décodage image (réutilise la logique de l'ancien FaceEngine)
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_image(payload):
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FaceEngineUnavailable(
                "OpenCV/NumPy manquants."
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
            raise FaceEngineError("Type d'image non supporté.")

        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise FaceEngineError("Image illisible.")
        return img

    # ------------------------------------------------------------------
    # Calcul embedding : YOLOv8 detection → ArcFace embedding
    # ------------------------------------------------------------------
    def compute_embedding(self, image_payload, pick: str = "largest",
                          run_liveness: bool = True) -> dict:
        """Détecte + extrait l'embedding 512D — interface identique à FaceEngine."""
        self._ensure_ready()
        img = self._decode_image(image_payload)

        # ── Détection YOLOv8 ──
        conf_thresh = float(self._cfg.get("MIN_DET_SCORE", 0.55))
        try:
            results = self._yolo.predict(img, conf=conf_thresh, verbose=False)
        except Exception as exc:
            raise FaceEngineError(f"YOLOv8 detection échouée : {exc}") from exc

        if not results or len(results[0].boxes) == 0:
            raise FaceEngineError(
                "Aucun visage détecté dans l'image (YOLOv8)."
            )

        # Convertit les boxes YOLO en liste de bbox
        boxes_xyxy = results[0].boxes.xyxy.cpu().numpy()
        scores = results[0].boxes.conf.cpu().numpy()
        n_faces = len(boxes_xyxy)

        # Sélection du visage
        if pick == "largest":
            idx = max(range(n_faces),
                      key=lambda i: (
                          (boxes_xyxy[i][2] - boxes_xyxy[i][0])
                          * (boxes_xyxy[i][3] - boxes_xyxy[i][1])
                      ))
        elif pick == "center":
            h, w = img.shape[:2]
            cx, cy = w / 2, h / 2
            idx = min(range(n_faces), key=lambda i: (
                ((boxes_xyxy[i][0] + boxes_xyxy[i][2]) / 2 - cx) ** 2
                + ((boxes_xyxy[i][1] + boxes_xyxy[i][3]) / 2 - cy) ** 2
            ))
        else:
            idx = 0

        bbox = boxes_xyxy[idx].astype(int).tolist()
        det_score = float(scores[idx])

        # ── Embedding ArcFace ──
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(img.shape[1], x2); y2 = min(img.shape[0], y2)
        face_crop = img[y1:y2, x1:x2]
        if face_crop.size == 0:
            raise FaceEngineError("Bbox visage hors image — détection invalide.")

        # InsightFace attend une face alignée 112x112 — on resize simplement.
        # Pour avoir un alignement précis il faudrait des landmarks (5pt) que
        # YOLOv8-face fournit dans certaines variantes (yolov8-face-lmk).
        try:
            import cv2
            aligned = cv2.resize(face_crop, (112, 112))
        except Exception as exc:
            raise FaceEngineError(f"Resize face crop échec : {exc}") from exc

        # Compute embedding
        try:
            if self._rec_via_analysis:
                # FaceAnalysis renvoie une liste d'objets Face — on passe le crop
                # directement et on prend le 1er retourné
                faces = self._rec_model.get(face_crop)
                if not faces:
                    raise FaceEngineError("ArcFace n'a pas trouvé de visage dans le crop.")
                emb = faces[0].normed_embedding
            else:
                # Direct model.get_feat() sur le crop aligné
                emb = self._rec_model.get_feat(aligned).flatten()
                # Normalise pour cosine
                import numpy as np
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
        except FaceEngineError:
            raise
        except Exception as exc:
            raise FaceEngineError(f"ArcFace embedding échec : {exc}") from exc

        embedding = [float(x) for x in emb.tolist()]

        # Score qualité composite : pour YOLOv8 on n'a pas de pose ; on utilise
        # juste det_score + ratio taille/image
        h, w = img.shape[:2]
        face_size_ratio = ((x2 - x1) * (y2 - y1)) / float(h * w)
        # bonus si visage occupe >5% de l'image
        size_bonus = min(1.0, face_size_ratio * 20)
        quality = round(0.7 * det_score + 0.3 * size_bonus, 4)

        return {
            "embedding": embedding,
            "embedding_dim": len(embedding),
            "model": "yolov8+arcface",
            "det_score": round(det_score, 4),
            "bbox": [int(v) for v in bbox],
            "pose": None,   # non fourni par YOLOv8-face nano
            "age": None,
            "gender": None,
            "quality": quality,
            "faces_detected": n_faces,
            "provider": self._provider_used,
        }


def get_face_engine():
    """Factory : renvoie le backend configuré (insightface ou yolov8).

    Usage dans le reste du code :
        from employees.face_engine_yolov8 import get_face_engine
        engine = get_face_engine()
        result = engine.compute_embedding(image)
    """
    backend = settings.KAYDAN_SHIELD.get("FACE", {}).get("BACKEND", "insightface").lower()
    if backend == "yolov8":
        return YoloV8FaceEngine.get_instance()
    # Fallback : ancien moteur InsightFace
    from .face_engine import FaceEngine
    if not hasattr(FaceEngine, "_singleton"):
        FaceEngine._singleton = FaceEngine()
    return FaceEngine._singleton
