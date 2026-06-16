"""Helpers ZKTeco — wrapper autour de pyzk pour les opérations courantes.

Tous les terminaux ZKTeco (K14, K20, K40, F18, MA300, iClock…) parlent le
même ZKAccess SDK sur le port 4370/TCP.

Usage :
    from devices.zk_client import ZkClient
    with ZkClient(ip="10.20.1.66").open() as zk:
        info = zk.info()
        attendances = zk.pull_attendances(since=last_sync)
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


class ZkUnavailable(RuntimeError):
    """Lib pyzk non installée."""


class ZkConnectionError(RuntimeError):
    """Échec de connexion / dialogue avec le terminal."""


class ZkClient:
    """Wrapper haut-niveau autour de pyzk avec gestion d'erreur cohérente."""

    def __init__(self, ip: str, port: int = 4370, password: int = 0,
                 timeout: int = 5, force_udp: bool = False):
        self.ip = ip
        self.port = port
        self.password = password
        self.timeout = timeout
        self.force_udp = force_udp
        self._zk = None
        self._conn = None

    def open(self):
        try:
            from zk import ZK
        except ImportError as exc:
            raise ZkUnavailable(
                "Module 'pyzk' non installé. Installer :  pip install pyzk"
            ) from exc
        self._zk = ZK(
            self.ip, port=self.port,
            timeout=self.timeout,
            password=self.password,
            force_udp=self.force_udp,
            ommit_ping=False,
        )
        try:
            self._conn = self._zk.connect()
        except Exception as exc:
            raise ZkConnectionError(
                f"Connexion ZKTeco {self.ip}:{self.port} échouée — {exc}"
            ) from exc
        return self

    def close(self):
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception:
                logger.debug("ZK disconnect failed", exc_info=True)
            self._conn = None

    def __enter__(self): return self.open()
    def __exit__(self, *exc):  self.close(); return False

    # ─── Read-only ──────────────────────────────────────────────────────
    def info(self) -> dict:
        """Retourne un dict d'infos device (firmware, serial, time, counts)."""
        c = self._conn
        info: dict = {}
        for key, fn in (
            ("firmware", c.get_firmware_version),
            ("serial",   c.get_serialnumber),
            ("name",     c.get_device_name),
            ("platform", c.get_platform),
            ("mac",      c.get_mac),
            ("time",     c.get_time),
        ):
            try:
                v = fn()
                info[key] = str(v) if v is not None else None
            except Exception as exc:
                logger.debug("ZK %s failed : %s", key, exc)
                info[key] = None
        # Compteurs
        try: info["users_count"] = len(c.get_users())
        except Exception: info["users_count"] = None
        try: info["fingerprints_count"] = len(c.get_templates())
        except Exception: info["fingerprints_count"] = None
        return info

    def pull_attendances(self, since: Optional[datetime] = None) -> list:
        """Renvoie tous les pointages stockés. Filtre par date si fourni.

        Chaque élément a : ``user_id``, ``timestamp``, ``status``, ``punch``.
        ZKTeco ne propose pas de "since" natif — on récupère tout et on filtre.
        """
        c = self._conn
        try:
            atts = c.get_attendance()
        except Exception as exc:
            raise ZkConnectionError(f"get_attendance failed : {exc}") from exc
        if since:
            # ZKTeco timestamps are naive — on naïve les deux côtés
            if hasattr(since, "tzinfo") and since.tzinfo is not None:
                since = since.replace(tzinfo=None)
            atts = [a for a in atts if a.timestamp > since]
        return atts

    def clear_attendances(self) -> None:
        """Vide la mémoire des pointages côté terminal (à appeler APRÈS sync sûre)."""
        try:
            self._conn.clear_attendance()
        except Exception as exc:
            raise ZkConnectionError(f"clear_attendance failed : {exc}") from exc

    def list_users(self) -> list:
        try:
            return self._conn.get_users()
        except Exception as exc:
            raise ZkConnectionError(f"get_users failed : {exc}") from exc

    # ─── Write ──────────────────────────────────────────────────────────
    def set_user(self, uid: int, name: str, card: int = 0,
                 password: str = "", privilege: int = 0,
                 group_id: str = "", user_id: Optional[str] = None) -> None:
        """Crée ou met à jour un utilisateur sur le terminal.

        Args:
            uid: ID interne (1-65535).
            name: nom affiché (max 24 caractères).
            card: numéro de carte RFID (entier décimal).
            password: code PIN éventuel.
            privilege: 0=normal user, 14=admin (constants pyzk).
            user_id: identifiant string (max 9 chars sur certains modèles).
        """
        try:
            from zk import const
        except ImportError as exc:
            raise ZkUnavailable("pyzk requis") from exc
        try:
            self._conn.set_user(
                uid=int(uid),
                name=str(name)[:24],
                privilege=privilege or const.USER_DEFAULT,
                password=str(password)[:8],
                group_id=str(group_id),
                user_id=str(user_id or uid)[:9],
                card=int(card or 0),
            )
        except Exception as exc:
            raise ZkConnectionError(f"set_user failed : {exc}") from exc

    def delete_user(self, uid: int) -> None:
        try:
            self._conn.delete_user(uid=int(uid))
        except Exception as exc:
            raise ZkConnectionError(f"delete_user failed : {exc}") from exc

    def restart(self) -> None:
        try:
            self._conn.restart()
        except Exception as exc:
            raise ZkConnectionError(f"restart failed : {exc}") from exc


def is_zkteco_device(device) -> bool:
    """Heuristique : True si l'équipement Shield est un terminal ZKTeco."""
    if not device or not device.model:
        return False
    brand = (device.model.brand or "").lower()
    if "zkteco" in brand or "zk teco" in brand or brand == "zk":
        return True
    # Quelques alias historiques
    return brand in ("anviz", "biopointer")  # même protocole sur ces marques


@contextmanager
def safe_zk_session(ip: str, port: int = 4370, password: int = 0,
                    timeout: int = 5) -> Iterator[Optional[ZkClient]]:
    """Context manager safe : yield un ZkClient ou None si pyzk manque/connexion KO.

    Utile dans le code qui doit "best-effort" interroger le terminal sans casser
    le flux principal si le terminal est offline.
    """
    client = ZkClient(ip, port=port, password=password, timeout=timeout)
    try:
        client.open()
        yield client
    except (ZkUnavailable, ZkConnectionError) as exc:
        logger.warning("ZK session impossible sur %s:%s — %s", ip, port, exc)
        yield None
    finally:
        client.close()
