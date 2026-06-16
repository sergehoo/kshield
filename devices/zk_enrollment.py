"""KAYDAN SHIELD — sessions d'enrôlement live pour terminaux ZKTeco.

Permet d'utiliser un K14/K20/F18 comme lecteur d'enrôlement de cartes RFID :

1. L'admin démarre une session via le UI (``POST /enroll-session/<pk>/start/``).
2. Un thread en arrière-plan ouvre une session pyzk ``live_capture()`` et
   pousse chaque event reçu dans l'inbox du device.
3. En parallèle, le thread snapshot la liste des users côté K14 au démarrage,
   puis re-fetche périodiquement pour détecter les ajouts manuels (admin tape
   sur le menu du K14 : User > Add > scan carte → un user temporaire est créé,
   on récupère sa carte et on l'ajoute à l'inbox).
4. La session s'arrête après ``duration`` secondes ou sur appel ``stop``.

Threading : on utilise un thread Python natif. C'est OK en dev runserver et
en prod gunicorn avec workers ASGI (uvicorn) car la session est I/O-bound
(socket TCP vers le terminal). En prod multi-worker, chaque worker gère ses
propres sessions — donc l'UI doit toujours hit le même worker pendant une
session (sticky session côté Traefik recommandé pour ``api.*``).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone as dt_tz
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


# Cache key partagée avec ScanInboxView (DON'T touch sans synchroniser)
_INBOX_KEY = "scan_inbox:reader:{}"
_INBOX_TTL = 600
_INBOX_MAX = 500


class EnrollmentSessionManager:
    """Singleton-process des sessions d'enrôlement actives par device."""

    _sessions: dict = {}   # device_id -> SessionContext
    _lock = threading.Lock()

    @classmethod
    def status(cls, device_id: int) -> dict:
        with cls._lock:
            s = cls._sessions.get(device_id)
            if not s or not s.thread.is_alive():
                return {"active": False}
            return {
                "active": True,
                "started_at": s.started_at.isoformat(),
                "duration_left": max(0, s.deadline - time.time()),
                "events_captured": s.events_captured,
            }

    @classmethod
    def start(cls, device, duration: int = 300) -> dict:
        """Lance une session d'enrôlement. Idempotent.

        Args:
            device: instance Device (déjà identifié comme ZKTeco).
            duration: durée max en secondes (default 5 min).

        Returns:
            dict avec status / message / device_id.
        """
        with cls._lock:
            existing = cls._sessions.get(device.pk)
            if existing and existing.thread.is_alive():
                return {
                    "status": "already_running",
                    "started_at": existing.started_at.isoformat(),
                    "duration_left": max(0, existing.deadline - time.time()),
                }

            ctx = _SessionContext(device=device, duration=duration)
            ctx.thread = threading.Thread(
                target=ctx.run,
                name=f"zk_enroll_{device.pk}",
                daemon=True,
            )
            ctx.thread.start()
            cls._sessions[device.pk] = ctx
            logger.info("ZK enrollment started for device %s (duration=%ds)",
                          device.pk, duration)
            return {
                "status": "started",
                "device_id": device.pk,
                "duration": duration,
                "started_at": ctx.started_at.isoformat(),
            }

    @classmethod
    def stop(cls, device_id: int) -> dict:
        with cls._lock:
            s = cls._sessions.get(device_id)
            if not s:
                return {"status": "not_running"}
            s.stop_event.set()
            return {
                "status": "stopping",
                "events_captured": s.events_captured,
            }


class _SessionContext:
    """État interne d'une session d'enrôlement."""

    def __init__(self, device, duration: int):
        self.device = device
        self.duration = duration
        self.started_at = timezone.now()
        self.deadline = time.time() + duration
        self.stop_event = threading.Event()
        self.events_captured = 0
        self.thread: Optional[threading.Thread] = None

    def _push(self, uid: str, ts, source: str, raw: Optional[dict] = None):
        """Ajoute un event à l'inbox du device."""
        if not uid:
            return
        key = _INBOX_KEY.format(self.device.pk)
        items = cache.get(key) or []
        # Dédup soft : si exact même uid dans les 2 dernières secondes, skip
        if items and items[-1].get("uid") == str(uid):
            try:
                last_ts = datetime.fromisoformat(items[-1]["timestamp"])
                now_ts = ts if hasattr(ts, "isoformat") else timezone.now()
                if (now_ts - last_ts).total_seconds() < 2:
                    return
            except Exception:
                pass
        items.append({
            "uid": str(uid),
            "timestamp": (ts if hasattr(ts, "isoformat") else timezone.now()).isoformat(),
            "source": source,
            "device_id": self.device.pk,
            "raw": raw or {},
        })
        if len(items) > _INBOX_MAX:
            items = items[-_INBOX_MAX:]
        cache.set(key, items, _INBOX_TTL)
        self.events_captured += 1

    def run(self):
        """Boucle simple : connect → snapshot → poll users toutes les 2s → diff.

        On N'UTILISE PAS `live_capture` qui (1) ne broadcaste pas les cartes
        inconnues sur la plupart des firmwares K14, (2) entre en conflit avec
        `get_users()` sur la même connexion.

        À la place on poll juste `get_users()` toutes les 2s et on détecte les
        ajouts/modifications. Le K14 demande à l'admin de faire ``Menu → User →
        Add → présenter carte`` pour enrôler — chaque ajout est détecté ici.
        """
        from .zk_client import ZkClient

        device = self.device
        pwd = 0
        if device.model and isinstance(device.model.spec, dict):
            pwd = int(device.model.spec.get("sdk_password", 0) or 0)

        client = None
        try:
            client = ZkClient(ip=device.ip_address, port=4370,
                                password=pwd, timeout=5)
            client.open()
        except Exception as exc:
            logger.warning("ZK enroll session open failed for %s: %s",
                            device.ip_address, exc)
            return

        conn = client._conn
        logger.info("ZK enroll loop started for device %s (deadline %ds)",
                      device.pk, self.duration)

        # Snapshot initial
        prev_users: dict = {}
        prev_card_ids: set = set()
        try:
            initial_users = conn.get_users()
            for u in initial_users:
                card = int(getattr(u, "card", 0) or 0)
                prev_users[str(u.user_id)] = {
                    "name": u.name, "card": card,
                }
                if card:
                    prev_card_ids.add(card)
            logger.info("ZK enroll initial snapshot: %d users, %d cards",
                          len(prev_users), len(prev_card_ids))
        except Exception as exc:
            logger.warning("Initial get_users failed: %s", exc)

        # Boucle de poll simple
        poll_interval = 2.0
        try:
            while not self.stop_event.is_set() and time.time() < self.deadline:
                time.sleep(poll_interval)
                try:
                    current_users = conn.get_users()
                except Exception as exc:
                    logger.warning("get_users in loop failed: %s — reconnect",
                                    exc)
                    # Tentative de reconnexion
                    try:
                        client.close()
                        client.open()
                        conn = client._conn
                        continue
                    except Exception:
                        logger.error("Reconnect failed, ending session")
                        break

                for u in current_users:
                    uid_str = str(u.user_id)
                    card = int(getattr(u, "card", 0) or 0)

                    # Nouveau user créé sur le terminal
                    if uid_str not in prev_users:
                        # Si carte présente, on push le n° de carte (utilisable directement
                        # comme uid badge). Sinon on push le user_id (fallback).
                        uid_push = str(card) if card else uid_str
                        self._push(uid_push, timezone.now(),
                                   source="zkteco_user_added", raw={
                            "user_id": uid_str, "name": u.name, "card": card,
                        })
                        prev_users[uid_str] = {"name": u.name, "card": card}
                        if card:
                            prev_card_ids.add(card)
                        logger.info(
                            "ZK NEW USER detected on %s: user_id=%s name=%r card=%s",
                            device.pk, uid_str, u.name, card,
                        )
                    # User existant + nouvelle carte assignée
                    elif card and card not in prev_card_ids:
                        self._push(str(card), timezone.now(),
                                   source="zkteco_card_assigned", raw={
                            "user_id": uid_str, "name": u.name, "card": card,
                        })
                        prev_card_ids.add(card)
                        prev_users[uid_str]["card"] = card
                        logger.info(
                            "ZK CARD assigned on %s: user_id=%s card=%s",
                            device.pk, uid_str, card,
                        )
        except Exception as exc:
            logger.warning("ZK enroll loop crashed on device %s: %s",
                            device.pk, exc, exc_info=True)
        finally:
            if client:
                try: client.close()
                except Exception: pass
            with EnrollmentSessionManager._lock:
                EnrollmentSessionManager._sessions.pop(device.pk, None)
            logger.info(
                "ZK enrollment ended for device %s (events=%d, duration=%ds)",
                device.pk, self.events_captured,
                int(time.time() - self.deadline + self.duration),
            )
