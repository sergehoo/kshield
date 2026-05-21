"""KAYDAN SHIELD — Anti-spoofing visage (SilentFace / MiniFASNet).

Implémentation de la stack `Silent-Face-Anti-Spoofing` (Minivision) qui combine
2 modèles ``MiniFASNet`` à scales différentes (2.7x et 4.0x autour du bbox).
On moyenne les softmax des 2 modèles avant argmax → classe finale + score.

**Pourquoi 2 modèles ?**
Un seul modèle a tendance à confondre l'arrière-plan ou les ombres avec un
fake. Le crop "large" (4×) regarde le contexte (cadre d'écran, mains tenant
une photo) alors que le crop "serré" (2.7×) regarde la texture du visage
(grain de peau vs lissé d'impression). L'ensemble est plus robuste.

**Classes (convention Silent-Face)** :
  - 0 → fake 2D (photo, écran imprimé)
  - 1 → real    (vraie personne)
  - 2 → fake 3D (masque silicone, papier mâché)

Le runtime ne charge pas TensorFlow ni PyTorch — uniquement ONNX Runtime.

**Téléchargement des poids** :
  python manage.py download_face_models
ou manuellement depuis le repo Silent-Face-Anti-Spoofing converti en ONNX.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class LivenessError(RuntimeError):
    """Erreur métier du module liveness."""


class LivenessUnavailable(LivenessError):
    """Modèles ONNX absents ou liveness désactivé."""


_lock = threading.Lock()
_detector: Optional["LivenessDetector"] = None


def get_detector() -> "LivenessDetector":
    """Singleton lazy-loaded — instancie au premier appel."""
    global _detector
    if _detector is not None:
        return _detector
    with _lock:
        if _detector is None:
            _detector = LivenessDetector()
        return _detector


class LivenessDetector:
    """Ensemble MiniFASNet (2 modèles, fusion softmax)."""

    INPUT_SIZE = 80  # taille d'entrée standard de MiniFASNet

    def __init__(self):
        cfg = settings.KAYDAN_SHIELD["FACE"].get("LIVENESS", {})
        self.enabled = bool(cfg.get("ENABLED", True))
        self.model_dir = cfg.get("MODEL_DIR", "")
        self.model_specs = list(cfg.get("MODELS", []))
        self.real_idx = int(cfg.get("REAL_CLASS_INDEX", 1))
        self.threshold = float(cfg.get("THRESHOLD", 0.70))
        self.block_enroll = bool(cfg.get("BLOCK_ENROLL_ON_SPOOF", True))
        # Liste de (scale, ort.InferenceSession) — peuplé au _ensure_ready
        self._sessions: list = []
        self._ready = False

    # ------------------------------------------------------------------
    # Init paresseuse
    # ------------------------------------------------------------------
    def _ensure_ready(self) -> None:
        if self._ready:
            return
        if not self.enabled:
            raise LivenessUnavailable("Anti-spoofing désactivé (FACE_LIVENESS_ENABLED=False).")
        try:
            import onnxruntime as ort  # noqa: F401
        except ImportError as exc:
            raise LivenessUnavailable(
                "onnxruntime manquant. `pip install onnxruntime`."
            ) from exc
        if not self.model_dir or not os.path.isdir(self.model_dir):
            raise LivenessUnavailable(
                f"Répertoire modèles introuvable : {self.model_dir!r}. "
                "Lancer `python manage.py download_face_models`."
            )

        # Charge chaque modèle de l'ensemble
        face_cfg = settings.KAYDAN_SHIELD["FACE"]
        providers = face_cfg.get("PROVIDERS") or ["CPUExecutionProvider"]
        sessions = []
        for fname, scale in self.model_specs:
            path = os.path.join(self.model_dir, fname)
            if not os.path.isfile(path):
                logger.warning("Modèle liveness manquant : %s (ignoré).", path)
                continue
            try:
                sess = ort.InferenceSession(path, providers=providers)
                sessions.append((float(scale), sess))
                logger.info("Liveness model chargé : %s (scale=%.2f)", fname, scale)
            except Exception as exc:
                logger.warning("Échec chargement %s : %s", path, exc)
        if not sessions:
            raise LivenessUnavailable(
                f"Aucun modèle MiniFASNet utilisable dans {self.model_dir}. "
                "Lancer `python manage.py download_face_models`."
            )

        self._sessions = sessions
        self._ready = True

    # ------------------------------------------------------------------
    # Préparation du crop pour MiniFASNet
    # ------------------------------------------------------------------
    @staticmethod
    def _crop_face_for_liveness(image_bgr, bbox, scale: float):
        """Étend le bbox par ``scale``, recadre l'image, resize en 80×80.

        bbox = [x1, y1, x2, y2] dans le repère image.
        Retourne un ndarray (80, 80, 3) BGR uint8 ou None si le crop est vide.
        """
        import cv2
        import numpy as np

        h, w = image_bgr.shape[:2]
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        bw = (x2 - x1) * scale
        bh = (y2 - y1) * scale
        # On force un carré (MiniFASNet attend du 1:1)
        side = max(bw, bh)
        nx1 = int(round(cx - side / 2))
        ny1 = int(round(cy - side / 2))
        nx2 = int(round(cx + side / 2))
        ny2 = int(round(cy + side / 2))
        # Clamp aux bornes image
        nx1, ny1 = max(0, nx1), max(0, ny1)
        nx2, ny2 = min(w, nx2), min(h, ny2)
        if nx2 - nx1 < 8 or ny2 - ny1 < 8:
            return None
        crop = image_bgr[ny1:ny2, nx1:nx2]
        try:
            crop = cv2.resize(crop, (LivenessDetector.INPUT_SIZE, LivenessDetector.INPUT_SIZE),
                              interpolation=cv2.INTER_LINEAR)
        except Exception:
            return None
        return crop

    @staticmethod
    def _softmax(x):
        import numpy as np
        e = np.exp(x - np.max(x))
        return e / e.sum()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------
    def check(self, image_bgr, bbox) -> dict:
        """Lance l'inférence anti-spoofing sur un visage déjà détecté.

        Args:
            image_bgr: ndarray HxWx3 BGR (sortie ``cv2.imdecode``).
            bbox: [x1, y1, x2, y2] dans le repère image.

        Returns:
            dict {
              "is_live":         bool,
              "real_score":      float 0-1 (score moyenné fusion),
              "predicted_class": int (0=fake_2D, 1=real, 2=fake_3D),
              "threshold":       float,
              "per_model":       [{"scale": float, "real_score": float, "class": int}, ...],
            }

        Raises:
            LivenessUnavailable : moteur off / poids absents.
            LivenessError       : crop invalide ou inférence ratée.
        """
        self._ensure_ready()
        import numpy as np

        per_model = []
        summed_probs = None
        for scale, sess in self._sessions:
            crop = self._crop_face_for_liveness(image_bgr, bbox, scale)
            if crop is None:
                continue
            # BGR → CHW float32 normalisé 0-1
            arr = crop.astype(np.float32) / 255.0
            arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...]  # 1×3×80×80
            try:
                input_name = sess.get_inputs()[0].name
                logits = sess.run(None, {input_name: arr})[0][0]
            except Exception as exc:
                raise LivenessError(f"Inférence MiniFASNet échouée : {exc}") from exc
            probs = self._softmax(logits)
            per_model.append({
                "scale": scale,
                "real_score": float(probs[self.real_idx]),
                "class": int(np.argmax(probs)),
            })
            summed_probs = probs if summed_probs is None else summed_probs + probs

        if summed_probs is None or not per_model:
            raise LivenessError("Aucun crop liveness valide (bbox trop petit ?).")

        fused = summed_probs / len(per_model)
        real_score = float(fused[self.real_idx])
        predicted_class = int(np.argmax(fused))
        is_live = predicted_class == self.real_idx and real_score >= self.threshold

        return {
            "is_live": bool(is_live),
            "real_score": round(real_score, 4),
            "predicted_class": predicted_class,
            "threshold": self.threshold,
            "per_model": per_model,
        }

    # ------------------------------------------------------------------
    # Statut (pour /face/status/)
    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "ready": self._ready,
            "model_dir": self.model_dir,
            "models_loaded": len(self._sessions) if self._ready else 0,
            "models_configured": len(self.model_specs),
            "threshold": self.threshold,
            "block_enroll_on_spoof": self.block_enroll,
        }
