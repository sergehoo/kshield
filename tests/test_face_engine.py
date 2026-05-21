"""KAYDAN SHIELD — Tests unitaires FaceEngine + cosine similarity.

Les vraies inférences InsightFace ne sont PAS testées ici (besoin GPU/ONNX
réel + modèles téléchargés). On teste :
  1. Le helper `_cosine_similarity` (math pure)
  2. La méthode `status()` (lazy, sans warm-up)
  3. La quality scoring `_compute_quality`
  4. Le décodage base64 → bytes
  5. La gestion d'erreur quand engine désactivé
"""
from __future__ import annotations

import base64

import pytest


# ---------------------------------------------------------------------------
# 1. Cosine similarity (math pure)
# ---------------------------------------------------------------------------
def test_cosine_similarity_identical_vectors():
    from employees.views import _cosine_similarity
    v = [0.1, 0.2, 0.3, 0.4]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    from employees.views import _cosine_similarity
    a = [1.0, 0.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0, 0.0]
    assert _cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite():
    from employees.views import _cosine_similarity
    a = [1.0, 1.0]
    b = [-1.0, -1.0]
    assert _cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector():
    from employees.views import _cosine_similarity
    assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


def test_cosine_similarity_dimension_mismatch():
    from employees.views import _cosine_similarity
    assert _cosine_similarity([1, 2], [1, 2, 3]) == 0.0


# ---------------------------------------------------------------------------
# 2. FaceEngine.status() — pas de warm-up déclenché
# ---------------------------------------------------------------------------
def test_status_returns_metadata():
    from employees.face_engine import FaceEngine
    eng = FaceEngine()
    st = eng.status()
    assert "enabled" in st
    assert "ready" in st
    assert "model" in st
    assert "providers" in st
    # ready=False car pas de _ensure_ready() appelé
    assert st["ready"] is False


def test_status_includes_liveness():
    from employees.face_engine import FaceEngine
    eng = FaceEngine()
    st = eng.status()
    assert "liveness" in st


# ---------------------------------------------------------------------------
# 3. Quality scoring
# ---------------------------------------------------------------------------
def test_quality_full_when_no_pose():
    from employees.face_engine import FaceEngine
    q = FaceEngine._compute_quality(det_score=0.95, pose=None)
    assert q == pytest.approx(0.95)


def test_quality_drops_with_high_yaw():
    from employees.face_engine import FaceEngine
    q_straight = FaceEngine._compute_quality(0.9, {"yaw": 0, "pitch": 0, "roll": 0})
    q_tilted = FaceEngine._compute_quality(0.9, {"yaw": 45, "pitch": 0, "roll": 0})
    assert q_tilted < q_straight
    assert q_tilted < 0.5


def test_quality_zero_below_min_det():
    from employees.face_engine import FaceEngine
    assert FaceEngine._compute_quality(0.1, None) == 0.0


def test_quality_zero_when_extreme_angle():
    from employees.face_engine import FaceEngine
    q = FaceEngine._compute_quality(0.9, {"yaw": 90, "pitch": 0, "roll": 0})
    assert q == 0.0


# ---------------------------------------------------------------------------
# 4. Décodage image (sans appel ONNX)
# ---------------------------------------------------------------------------
def test_decode_data_url_with_prefix():
    """_decode_image accepte data:image/jpeg;base64,..."""
    pytest.importorskip("cv2")  # skip si OpenCV pas installé
    import cv2
    import numpy as np
    from employees.face_engine import FaceEngine
    # Génère une image valide 10x10 noire en JPEG
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    b64 = base64.b64encode(buf.tobytes()).decode()
    data_url = f"data:image/jpeg;base64,{b64}"
    decoded = FaceEngine._decode_image(data_url)
    assert decoded.shape == (10, 10, 3)


def test_decode_invalid_base64_raises():
    from employees.face_engine import FaceEngine, FaceEngineError
    pytest.importorskip("cv2")
    with pytest.raises(FaceEngineError):
        FaceEngine._decode_image("not-base64-at-all-@@@@")


# ---------------------------------------------------------------------------
# 5. Engine désactivé via settings
# ---------------------------------------------------------------------------
def test_engine_disabled_raises_unavailable(settings):
    from employees.face_engine import FaceEngine, FaceEngineUnavailable
    settings.KAYDAN_SHIELD = {**settings.KAYDAN_SHIELD, "FACE": {
        **settings.KAYDAN_SHIELD["FACE"], "ENABLED": False,
    }}
    eng = FaceEngine()
    with pytest.raises(FaceEngineUnavailable):
        eng._ensure_ready()
