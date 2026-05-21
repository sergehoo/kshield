"""KAYDAN SHIELD — Worker caméras IP (broadcaster Redis + pipeline IA).

Architecture :

    ┌────────────────────────────────────────────────────────────────┐
    │  python manage.py run_camera_workers                           │
    │                                                                │
    │  Boucle principale (toutes les 60s)                            │
    │   ├─ Charge Camera.objects.filter(is_active=True)              │
    │   ├─ Spawn 1 thread par caméra nouvelle                        │
    │   └─ Termine les threads des caméras supprimées/désactivées    │
    │                                                                │
    │  Thread par caméra :                                           │
    │   1. cv2.VideoCapture(rtsp_url)                                │
    │   2. boucle de lecture (target_fps)                            │
    │   3. JPEG encode + r.publish(camera:<id>:frames, jpeg)         │
    │   4. r.set(camera:<id>:alive, "1", ex=10)  # heartbeat         │
    │   5. (option) toutes les N frames :                            │
    │       - InsightFace match → FaceSightingEvent                  │
    │       - service confirm_attendance_from_sighting               │
    └────────────────────────────────────────────────────────────────┘

Déploiement prod : tourne en service systemd / Docker compose à part de
l'app Django. Un seul process pour toutes les caméras (multi-thread).
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Dict

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class CameraThread(threading.Thread):
    """Thread dédié à 1 caméra : lecture RTSP → publish Redis + pipeline IA."""

    HEARTBEAT_INTERVAL = 3.0  # secondes entre 2 SET alive
    AI_EVERY_N_FRAMES = 30    # 1 inférence visage toutes les ~3s à 10fps
    DB_RELOAD_EVERY = 60.0    # recharge la conf caméra depuis la DB

    def __init__(self, camera_id: int, with_face: bool = True):
        super().__init__(daemon=True, name=f"cam-{camera_id}")
        self.camera_id = camera_id
        self.with_face = with_face
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        from devices.models import Camera
        from devices.streaming import (camera_alive_key, camera_channel,
                                          open_capture)

        try:
            import cv2
        except ImportError:
            logger.error("Camera %s: OpenCV manquant.", self.camera_id)
            return

        try:
            import redis
            from django.conf import settings
            r = redis.Redis.from_url(
                getattr(settings, "REDIS_URL", None) or "redis://127.0.0.1:6379/0",
            )
        except Exception as exc:
            logger.error("Camera %s: Redis init échouée: %s", self.camera_id, exc)
            return

        cam = None
        cap = None
        last_db_reload = 0.0
        last_heartbeat = 0.0
        frame_count = 0

        try:
            while not self._stop.is_set():
                # Recharge la conf caméra périodiquement
                now = time.time()
                if cam is None or now - last_db_reload > self.DB_RELOAD_EVERY:
                    try:
                        cam = Camera.objects.select_related("site", "zone").get(
                            pk=self.camera_id,
                        )
                    except Camera.DoesNotExist:
                        logger.info("Camera %s: supprimée, arrêt thread.", self.camera_id)
                        return
                    if not cam.is_active:
                        logger.info("Camera %s: désactivée, arrêt thread.", self.camera_id)
                        return
                    last_db_reload = now

                # Ouvre / ré-ouvre la connexion RTSP si nécessaire
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                    cap, err = open_capture(cam)
                    if err or cap is None or not cap.isOpened():
                        logger.warning("Camera %s: open échec (%s) — retry 5s.",
                                        self.camera_id, err)
                        Camera.objects.filter(pk=self.camera_id).update(
                            status="error", last_error=err[:240] or "open failed",
                        )
                        time.sleep(5.0)
                        continue
                    Camera.objects.filter(pk=self.camera_id).update(
                        status="online", last_error="",
                    )

                # Lecture frame
                ok, frame = cap.read()
                if not ok or frame is None:
                    logger.debug("Camera %s: frame perdue.", self.camera_id)
                    time.sleep(0.05)
                    # Forcer ré-ouverture après 30 échecs
                    cap.release()
                    cap = None
                    continue

                # Downscale + encode JPEG
                tw = int(cam.target_width or 1280)
                if frame.shape[1] > tw:
                    nh = int(frame.shape[0] * tw / frame.shape[1])
                    frame = cv2.resize(frame, (tw, nh))
                ok, buf = cv2.imencode(".jpg", frame, [
                    cv2.IMWRITE_JPEG_QUALITY, int(cam.jpeg_quality or 75),
                ])
                if not ok:
                    continue
                jpeg = buf.tobytes()

                # Publish + heartbeat
                try:
                    r.publish(camera_channel(self.camera_id), jpeg)
                    if now - last_heartbeat > self.HEARTBEAT_INTERVAL:
                        r.setex(camera_alive_key(self.camera_id), 10, "1")
                        last_heartbeat = now
                except Exception as exc:
                    logger.warning("Camera %s: Redis publish échoué: %s",
                                    self.camera_id, exc)

                # Pipeline IA (face recognition + confirmation présence)
                frame_count += 1
                if (self.with_face and cam.enable_face_recognition
                        and frame_count % self.AI_EVERY_N_FRAMES == 0):
                    try:
                        self._run_face_pipeline(cam, frame)
                    except Exception:
                        logger.exception("Camera %s: face pipeline échec",
                                          self.camera_id)

                # Throttle pour respecter target_fps
                target_fps = max(1, min(30, int(cam.target_fps or 10)))
                time.sleep(max(0.0, 1.0 / target_fps - 0.005))

        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            try:
                r.delete(camera_alive_key(self.camera_id))
            except Exception:
                pass
            logger.info("Camera %s: thread terminé proprement.", self.camera_id)

    # ------------------------------------------------------------------
    def _run_face_pipeline(self, cam, frame_bgr):
        """InsightFace → sighting + confirmation présence.

        Best-effort : tout échec est logué mais ne stoppe pas le streaming.
        """
        try:
            from employees.face_engine import (FaceEngineError,
                                                 FaceEngineUnavailable,
                                                 get_engine)
        except ImportError:
            return

        try:
            import cv2
            ok, jpeg_buf = cv2.imencode(".jpg", frame_bgr,
                                           [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                return
            engine = get_engine()
            res = engine.compute_embedding(jpeg_buf.tobytes())
        except FaceEngineUnavailable:
            return  # silent: engine désactivé
        except FaceEngineError:
            return  # pas de visage détecté → normal
        except Exception:
            logger.exception("Camera %s: compute_embedding KO", self.camera_id)
            return

        # Match contre les FaceProfile actifs
        try:
            from employees.models import FaceProfile
            from employees.views import _cosine_similarity
            embedding = res["embedding"]
            best_score = -1.0
            best_profile = None
            for prof in FaceProfile.objects.filter(
                is_active=True, embedding_dim=len(embedding),
            ).select_related("employee", "employee__company"):
                try:
                    s = _cosine_similarity(embedding, prof.embedding)
                except Exception:
                    continue
                if s > best_score:
                    best_score, best_profile = s, prof
        except Exception:
            logger.exception("Camera %s: match KO", self.camera_id)
            return

        # Threshold via settings (sinon 0.60)
        from django.conf import settings
        threshold = float(settings.KAYDAN_SHIELD["FACE"].get("MATCH_THRESHOLD", 0.60))
        matched = bool(best_profile and best_score >= threshold)

        # Persiste sighting + confirmation
        try:
            from attendance.models import FaceSightingEvent
            from attendance.services_face import confirm_attendance_from_sighting
            from django.utils import timezone
            sighting = FaceSightingEvent.objects.create(
                camera=cam,
                site=cam.site,
                employee=best_profile.employee if matched else None,
                face_score=round(float(best_score), 4) if best_profile else 0.0,
                liveness_score=(res.get("liveness") or {}).get("real_score"),
                bbox=res.get("bbox") or [],
                matched=matched,
                timestamp=timezone.now(),
            )
            if matched:
                confirm_attendance_from_sighting(sighting)
        except Exception:
            logger.exception("Camera %s: persist sighting KO", self.camera_id)


# ---------------------------------------------------------------------------
# Commande Django
# ---------------------------------------------------------------------------
class Command(BaseCommand):
    help = ("Lance les workers caméras IP : 1 thread par caméra qui lit RTSP, "
            "publie sur Redis pub/sub et exécute le pipeline IA visage.")

    def add_arguments(self, parser):
        parser.add_argument("--camera", type=int, default=None,
                            help="Démarre uniquement la caméra <id>.")
        parser.add_argument("--no-face", action="store_true",
                            help="Désactive le pipeline face recognition.")
        parser.add_argument("--reload-interval", type=int, default=60,
                            help="Intervalle (s) entre rechargements DB.")

    def handle(self, *args, **opts):
        from devices.models import Camera

        with_face = not opts["no_face"]
        only_camera = opts["camera"]
        reload_every = opts["reload_interval"]

        self.stdout.write(self.style.NOTICE(
            f"-> Démarrage workers caméras (face={with_face}, "
            f"reload={reload_every}s)"
        ))

        threads: Dict[int, CameraThread] = {}
        stop_event = threading.Event()

        def _shutdown(signum, _frame):
            self.stdout.write(self.style.WARNING(
                f"\nSignal {signum} reçu — arrêt propre…"
            ))
            stop_event.set()
            for t in threads.values():
                t.stop()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        last_scan = 0.0
        while not stop_event.is_set():
            now = time.time()
            if now - last_scan > reload_every:
                # Inventaire des caméras à gérer
                qs = Camera.objects.filter(is_active=True)
                if only_camera is not None:
                    qs = qs.filter(pk=only_camera)
                target_ids = set(qs.values_list("pk", flat=True))
                current_ids = set(threads.keys())

                # Spawn des nouvelles
                for cid in target_ids - current_ids:
                    self.stdout.write(self.style.SUCCESS(f"  [+] thread cam-{cid}"))
                    t = CameraThread(cid, with_face=with_face)
                    threads[cid] = t
                    t.start()
                # Stop des retirées
                for cid in current_ids - target_ids:
                    self.stdout.write(self.style.WARNING(f"  [-] stop cam-{cid}"))
                    threads[cid].stop()
                    threads[cid].join(timeout=5.0)
                    del threads[cid]
                # Nettoie les morts
                for cid in list(threads.keys()):
                    if not threads[cid].is_alive():
                        self.stdout.write(self.style.WARNING(f"  [x] cam-{cid} mort, respawn"))
                        del threads[cid]
                last_scan = now
            time.sleep(2.0)

        # Cleanup final
        for t in threads.values():
            t.join(timeout=5.0)
        self.stdout.write(self.style.SUCCESS("✓ Tous les threads stoppés."))
