"""KAYDAN SHIELD — Streaming caméras (Redis broadcaster + RTSP fallback).

Deux modes :

1. **Production multi-utilisateurs** (1 worker RTSP → N abonnés HTTP)
   - Un process `run_camera_workers` ouvre 1 connexion RTSP par caméra.
   - Les frames JPEG sont publiées sur Redis pub/sub : ``camera:<id>:frames``.
   - Chaque ``CameraStreamView`` consomme du Redis pub/sub. Pas de re-encode,
     pas de N×RTSP, pas de duplication CPU.

2. **Dev / single-user** (fallback)
   - Si pas de worker actif, ``CameraStreamView`` ouvre directement le RTSP
     via OpenCV (mode legacy). Pratique pour bricoler en local.

Détection du worker : le worker publie un heartbeat sur la clé Redis
``camera:<id>:alive`` avec TTL 10s. Si la clé existe → on consomme du pubsub,
sinon → fallback RTSP direct.
"""
from __future__ import annotations

import logging
import time
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers Redis (lazy import — Redis optionnel pour dev)
# ---------------------------------------------------------------------------
def _get_redis():
    """Retourne un client Redis ou None si indisponible."""
    try:
        import redis
        from django.conf import settings
        url = getattr(settings, "REDIS_URL", None) or "redis://127.0.0.1:6379/0"
        return redis.Redis.from_url(url, socket_connect_timeout=2,
                                      socket_timeout=2)
    except Exception:
        return None


def camera_channel(camera_id: int) -> str:
    return f"camera:{camera_id}:frames"


def camera_alive_key(camera_id: int) -> str:
    return f"camera:{camera_id}:alive"


def is_worker_alive(camera_id: int) -> bool:
    """Vérifie si un worker pub-side est actif pour cette caméra."""
    r = _get_redis()
    if not r:
        return False
    try:
        return bool(r.exists(camera_alive_key(camera_id)))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Capture directe (mode dev / fallback / snapshot)
# ---------------------------------------------------------------------------
def open_capture(camera, transport_override: Optional[str] = None):
    """Ouvre une cv2.VideoCapture sur l'URL effective."""
    try:
        import cv2
    except ImportError:
        return None, "OpenCV non installé."
    import os
    transport = transport_override or camera.transport or "tcp"
    os.environ.setdefault(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        f"rtsp_transport;{transport}|stimeout;5000000|max_delay;500000",
    )
    cap = cv2.VideoCapture(camera.effective_rtsp_url, cv2.CAP_FFMPEG)
    if not cap or not cap.isOpened():
        return cap, f"Impossible d'ouvrir le flux ({transport.upper()})."
    return cap, ""


def capture_snapshot(camera, timeout_sec: float = 8.0):
    """Capture une seule frame (pour test + thumbnails)."""
    try:
        import cv2
    except ImportError:
        return None, "OpenCV non installé."
    cap, err = open_capture(camera)
    if err:
        return None, err
    start = time.time()
    frame = None
    try:
        while time.time() - start < timeout_sec:
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
                break
            time.sleep(0.1)
    finally:
        try:
            cap.release()
        except Exception:
            pass
    if frame is None:
        return None, "Aucune frame reçue (RTSP timeout)."
    if frame.shape[1] > camera.target_width:
        new_h = int(frame.shape[0] * camera.target_width / frame.shape[1])
        frame = cv2.resize(frame, (camera.target_width, new_h))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY,
                                             int(camera.jpeg_quality or 80)])
    if not ok:
        return None, "Échec encodage JPEG."
    return bytes(buf), ""


# ---------------------------------------------------------------------------
# Streaming MJPEG — fallback RTSP direct
# ---------------------------------------------------------------------------
_BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "


def _wrap_frame(jpeg: bytes) -> bytes:
    return (_BOUNDARY + str(len(jpeg)).encode() + b"\r\n\r\n"
            + jpeg + b"\r\n")


def stream_camera_direct(camera, max_seconds: int = 3600) -> Iterator[bytes]:
    """Lit RTSP en direct (1 connexion par client). Mode dev / fallback."""
    try:
        import cv2
    except ImportError:
        return
    cap, err = open_capture(camera)
    if err or cap is None or not cap.isOpened():
        logger.warning("Camera %s: flux indisponible (%s)", camera.pk, err)
        return
    target_fps = max(1, min(30, int(getattr(camera, "target_fps", 10) or 10)))
    frame_interval = 1.0 / target_fps
    target_width = int(getattr(camera, "target_width", 1280) or 1280)
    jpeg_q = int(getattr(camera, "jpeg_quality", 75) or 75)
    start = time.time()
    last_emit = 0.0
    consecutive_failures = 0
    try:
        while time.time() - start < max_seconds:
            now = time.time()
            if now - last_emit < frame_interval:
                time.sleep(0.005)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                if consecutive_failures > 30:
                    break
                time.sleep(0.05)
                continue
            consecutive_failures = 0
            if frame.shape[1] > target_width:
                new_h = int(frame.shape[0] * target_width / frame.shape[1])
                frame = cv2.resize(frame, (target_width, new_h))
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_q])
            if not ok:
                continue
            yield _wrap_frame(buf.tobytes())
            last_emit = now
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        logger.debug("Camera %s: client déconnecté.", camera.pk)
    finally:
        try:
            cap.release()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Streaming MJPEG — relais Redis (1 RTSP → N clients)
# ---------------------------------------------------------------------------
def stream_camera_from_redis(camera, max_seconds: int = 3600) -> Iterator[bytes]:
    """Consomme les frames JPEG publiées par le worker sur Redis pub/sub.

    Si Redis pète en cours, le générateur termine proprement et le client peut
    se reconnecter (le navigateur le fait automatiquement sur <img>).
    """
    r = _get_redis()
    if r is None:
        logger.warning("Camera %s: Redis indispo, fallback direct.", camera.pk)
        yield from stream_camera_direct(camera, max_seconds)
        return

    channel = camera_channel(camera.pk)
    try:
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel)
    except Exception as exc:
        logger.warning("Camera %s: subscribe Redis échoué (%s) — fallback direct.",
                        camera.pk, exc)
        yield from stream_camera_direct(camera, max_seconds)
        return

    start = time.time()
    try:
        for msg in pubsub.listen():
            if time.time() - start > max_seconds:
                break
            if msg is None or msg.get("type") != "message":
                continue
            jpeg = msg.get("data")
            if not jpeg:
                continue
            yield _wrap_frame(jpeg)
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        logger.debug("Camera %s: client Redis déconnecté.", camera.pk)
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception:
            pass


def stream_camera(camera, max_seconds: int = 3600) -> Iterator[bytes]:
    """Point d'entrée principal : Redis si worker actif, sinon RTSP direct.

    Tout échec (Redis down, RTSP timeout, etc.) → on log et on termine
    le générateur proprement. Le navigateur affichera "flux indisponible".
    """
    try:
        use_redis = is_worker_alive(camera.pk)
    except Exception as exc:
        logger.warning("is_worker_alive() a planté (cam=%s): %s — fallback direct.",
                        camera.pk, exc)
        use_redis = False

    if use_redis:
        logger.debug("Camera %s: streaming via Redis.", camera.pk)
        try:
            yield from stream_camera_from_redis(camera, max_seconds)
        except Exception as exc:
            logger.warning("Stream Redis crashed (cam=%s): %s — fallback direct.",
                            camera.pk, exc)
            try:
                yield from stream_camera_direct(camera, max_seconds)
            except Exception as exc2:
                logger.exception("Stream direct fallback aussi en échec (cam=%s): %s",
                                  camera.pk, exc2)
                return
    else:
        logger.debug("Camera %s: streaming RTSP direct (pas de worker).", camera.pk)
        try:
            yield from stream_camera_direct(camera, max_seconds)
        except Exception as exc:
            logger.exception("Stream direct a échoué (cam=%s): %s", camera.pk, exc)
            return
