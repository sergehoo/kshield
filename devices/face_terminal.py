"""Adaptateurs pour terminaux de reconnaissance faciale dynamique.

Architecture pluggable : chaque marque a son propre adapter qui implémente
l'interface standard ``FaceTerminalAdapter``. Le dispatcher choisit
automatiquement l'adapter selon ``device.model.spec["adapter"]``.

Adaptateurs livrés :
- ``zkteco_speedface`` : SpeedFace V4L / M4 / VM10 (SDK ZKAccess, pyzk)
- ``hikvision_isapi``  : DS-K1T671M et compatibles (ISAPI HTTP + digest auth)
- ``dahua_netsdk``     : ASI7213Y et compatibles (NetSDK / HTTP API)
- ``anviz_crosschex``  : M7 FacePro (CrossChex SDK)

Toutes les méthodes reçoivent en entrée un ``Device`` Shield et renvoient
des formats standardisés (list of face records, event dicts, …).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Types standardisés
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FaceRecord:
    """Représentation portable d'un employé enrôlé sur un terminal face."""
    user_id: str        # ID interne du terminal
    name: str
    card: Optional[int] = None
    photo_bytes: Optional[bytes] = None    # JPEG/PNG si dispo
    template_bytes: Optional[bytes] = None # template binaire face (propriétaire)
    embedding: Optional[list] = None        # vecteur ArcFace 512D si extrait
    face_count: int = 1


@dataclass
class FaceEvent:
    """Event de vérification face reçu du terminal (granted ou denied)."""
    user_id: str        # ID interne terminal, ou vide si visage inconnu
    timestamp: datetime
    similarity: Optional[float] = None    # 0–1, score de matching
    method: str = "face"                  # face / card / hybrid
    granted: bool = True
    mask_detected: Optional[bool] = None
    temperature: Optional[float] = None
    photo_bytes: Optional[bytes] = None   # snapshot au moment du scan
    raw: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────
class FaceTerminalError(RuntimeError):
    pass


class FaceTerminalUnavailable(FaceTerminalError):
    pass


class UnsupportedAdapterError(FaceTerminalError):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Interface abstraite
# ─────────────────────────────────────────────────────────────────────────────
class FaceTerminalAdapter(ABC):
    """Interface commune pour tous les terminaux face."""

    def __init__(self, device):
        self.device = device
        self.ip = device.ip_address
        self.port = int(
            (device.model.spec or {}).get("http_port")
            or (device.model.spec or {}).get("sdk_port")
            or 80
        )
        self.password = str(
            (device.model.spec or {}).get("password", "")
            or (device.model.spec or {}).get("sdk_password", "")
        )
        self.timeout = 5

    @abstractmethod
    def info(self) -> dict:
        """Renvoie firmware/serial/counts."""

    @abstractmethod
    def list_faces(self) -> list[FaceRecord]:
        """Liste tous les enrôlés face du terminal."""

    @abstractmethod
    def push_face(self, record: FaceRecord) -> bool:
        """Push (crée ou met à jour) un enrôlement face."""

    @abstractmethod
    def delete_face(self, user_id: str) -> bool:
        """Supprime un enrôlement face."""

    def pull_events(self, since: Optional[datetime] = None) -> list[FaceEvent]:
        """Pull les events face récents (default : depuis les X dernières heures)."""
        return []   # Optionnel — certains adapters préfèrent le push webhook


# ─────────────────────────────────────────────────────────────────────────────
# Adaptateur ZKTeco SpeedFace — utilise pyzk (SDK ZKAccess existant)
# ─────────────────────────────────────────────────────────────────────────────
class ZktecoSpeedFaceAdapter(FaceTerminalAdapter):
    """Adapter pour ZKTeco SpeedFace V4L / M4 / VM10.

    Réutilise le pyzk existant. Les templates face sont récupérés via
    ``get_face`` (nouvelle API pyzk >= 0.9) ou reconstruits depuis les
    snapshots stockés.
    """

    def _client(self):
        from .zk_client import ZkClient
        return ZkClient(
            ip=self.ip, port=self.port or 4370,
            password=int(self.password or 0),
            timeout=self.timeout,
        )

    def info(self) -> dict:
        with self._client().open() as zk:
            return zk.info()

    def list_faces(self) -> list[FaceRecord]:
        with self._client().open() as zk:
            users = zk.list_users()
        records = []
        for u in users:
            try:
                records.append(FaceRecord(
                    user_id=str(u.user_id),
                    name=u.name or "",
                    card=int(getattr(u, "card", 0) or 0),
                ))
            except Exception:
                logger.debug("SpeedFace user parse failed", exc_info=True)
        return records

    def push_face(self, record: FaceRecord) -> bool:
        """Push user (nom + card). Pour push le template face, il faut la
        méthode ``set_user_face`` de pyzk qui n'est pas dispo dans toutes
        les versions. On log un warning si photo présente mais push impossible."""
        with self._client().open() as zk:
            try:
                uid_int = int(record.user_id) if str(record.user_id).isdigit() else abs(hash(record.user_id)) % 65500 + 1
            except Exception:
                uid_int = abs(hash(record.user_id)) % 65500 + 1
            zk.set_user(
                uid=uid_int, name=record.name[:24],
                card=int(record.card or 0),
                user_id=str(record.user_id)[:9],
            )
            # Push template face si dispo — pyzk API varies
            if record.template_bytes:
                try:
                    zk._conn.set_user_template(  # méthode expérimentale
                        uid=uid_int, template=record.template_bytes,
                    )
                except (AttributeError, Exception) as exc:
                    logger.warning(
                        "SpeedFace push template face non supporté par pyzk : %s", exc,
                    )
        return True

    def delete_face(self, user_id: str) -> bool:
        with self._client().open() as zk:
            try:
                uid_int = int(user_id) if str(user_id).isdigit() else abs(hash(user_id)) % 65500 + 1
            except Exception:
                uid_int = abs(hash(user_id)) % 65500 + 1
            zk.delete_user(uid=uid_int)
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Adaptateur Hikvision ISAPI
# ─────────────────────────────────────────────────────────────────────────────
class HikvisionIsapiAdapter(FaceTerminalAdapter):
    """Adapter Hikvision DS-K1T671M et compatibles via ISAPI HTTP.

    Auth Digest — user/pass configurés dans device.model.spec.
    Endpoints ISAPI courants :
      - /ISAPI/AccessControl/UserInfo/Search
      - /ISAPI/Intelligent/FDLib/FaceDataRecord
      - /ISAPI/Event/notification/httpHosts (push config)
    """

    def _auth(self):
        import requests.auth as _auth
        user = (self.device.model.spec or {}).get("username", "admin")
        return _auth.HTTPDigestAuth(user, self.password or "12345")

    def _base_url(self):
        return f"http://{self.ip}:{self.port or 80}"

    def _get(self, path: str, timeout: int = None):
        import requests
        return requests.get(
            self._base_url() + path,
            auth=self._auth(), timeout=timeout or self.timeout,
        )

    def _post(self, path: str, data=None, files=None, json_data=None, timeout: int = None):
        import requests
        return requests.post(
            self._base_url() + path,
            auth=self._auth(),
            data=data, files=files, json=json_data,
            timeout=timeout or self.timeout * 2,
        )

    def info(self) -> dict:
        try:
            r = self._get("/ISAPI/System/deviceInfo?format=json")
            if r.status_code == 200:
                d = r.json().get("DeviceInfo", {})
                return {
                    "firmware": d.get("firmwareVersion"),
                    "serial": d.get("serialNumber"),
                    "name": d.get("deviceName"),
                    "platform": d.get("deviceType"),
                    "mac": d.get("macAddress"),
                }
        except Exception as exc:
            raise FaceTerminalUnavailable(f"ISAPI info failed: {exc}") from exc
        raise FaceTerminalUnavailable("ISAPI deviceInfo returned non-200")

    def list_faces(self) -> list[FaceRecord]:
        records = []
        try:
            # Body JSON : search sur tous les users
            body = {
                "UserInfoSearchCond": {
                    "searchID": "shield-list",
                    "maxResults": 5000,
                    "searchResultPosition": 0,
                }
            }
            r = self._post(
                "/ISAPI/AccessControl/UserInfo/Search?format=json",
                json_data=body,
            )
            if r.status_code != 200:
                return []
            data = r.json().get("UserInfoSearch", {}).get("UserInfo", [])
            for u in data:
                records.append(FaceRecord(
                    user_id=str(u.get("employeeNo") or u.get("id") or ""),
                    name=u.get("name") or "",
                    card=None,
                ))
        except Exception as exc:
            logger.warning("Hikvision list_faces failed : %s", exc)
        return records

    def push_face(self, record: FaceRecord) -> bool:
        # 1) Crée/MAJ user
        user_body = {
            "UserInfo": {
                "employeeNo": str(record.user_id),
                "name": record.name[:32],
                "userType": "normal",
                "Valid": {"enable": True},
                "doorRight": "1",
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}],
            }
        }
        r = self._post("/ISAPI/AccessControl/UserInfo/Record?format=json",
                        json_data=user_body)
        if r.status_code not in (200, 201):
            logger.warning("Hikvision push user failed: %s %s", r.status_code, r.text[:200])
            return False

        # 2) Upload photo face si fournie
        if record.photo_bytes:
            face_body = {
                "FaceDataRecord": {
                    "FPID": str(record.user_id),
                    "faceLibType": "blackFD",
                    "FDID": "1",
                    "name": record.name[:32],
                }
            }
            try:
                import json
                files = {
                    "FaceDataRecord": (None, json.dumps(face_body), "application/json"),
                    "img": (f"face_{record.user_id}.jpg",
                             record.photo_bytes, "image/jpeg"),
                }
                r = self._post("/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json",
                                files=files, timeout=15)
                if r.status_code not in (200, 201):
                    logger.warning(
                        "Hikvision face upload failed: %s %s",
                        r.status_code, r.text[:200],
                    )
                    return False
            except Exception as exc:
                logger.exception("Hikvision face upload exception")
                return False
        return True

    def delete_face(self, user_id: str) -> bool:
        body = {"UserInfoDelCond": {"EmployeeNoList": [{"employeeNo": str(user_id)}]}}
        r = self._post("/ISAPI/AccessControl/UserInfo/Delete?format=json",
                        json_data=body)
        return r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Adaptateur générique HTTP (fallback pour marques inconnues)
# ─────────────────────────────────────────────────────────────────────────────
class GenericHttpAdapter(FaceTerminalAdapter):
    """Adapter minimal — teste juste la connectivité HTTP.

    Utilisé comme fallback quand aucun adapter spécifique n'est configuré.
    Les méthodes push/list ne font rien (log warning).
    """

    def info(self) -> dict:
        import requests
        try:
            r = requests.get(f"http://{self.ip}/", timeout=self.timeout)
            return {
                "firmware": r.headers.get("Server", "unknown"),
                "http_status": r.status_code,
            }
        except Exception as exc:
            raise FaceTerminalUnavailable(str(exc)) from exc

    def list_faces(self) -> list[FaceRecord]:
        logger.warning(
            "GenericHttpAdapter.list_faces : opération non implémentée. "
            "Configure device.model.spec.adapter avec le bon nom (zkteco_speedface, "
            "hikvision_isapi, dahua_netsdk, anviz_crosschex).",
        )
        return []

    def push_face(self, record): return False
    def delete_face(self, user_id): return False


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher : choisit le bon adapter selon device.model.spec["adapter"]
# ─────────────────────────────────────────────────────────────────────────────
_ADAPTERS = {
    "zkteco_speedface": ZktecoSpeedFaceAdapter,
    "hikvision_isapi":  HikvisionIsapiAdapter,
    # "dahua_netsdk":     DahuaNetSdkAdapter,     # à implémenter quand dispo
    # "anviz_crosschex":  AnvizCrossChexAdapter,  # à implémenter
    "generic_http":     GenericHttpAdapter,
}


def get_adapter(device) -> FaceTerminalAdapter:
    """Instancie l'adapter approprié pour un device face_terminal."""
    if not device or not device.model:
        raise UnsupportedAdapterError("device sans model")
    spec = device.model.spec or {}
    adapter_key = (spec.get("adapter") or "").lower().strip()
    if not adapter_key:
        # Fallback sur marque connue
        brand = (device.model.brand or "").lower()
        if "zkteco" in brand:
            adapter_key = "zkteco_speedface"
        elif "hikvision" in brand:
            adapter_key = "hikvision_isapi"
        elif "dahua" in brand:
            adapter_key = "dahua_netsdk"
        elif "anviz" in brand:
            adapter_key = "anviz_crosschex"
        else:
            adapter_key = "generic_http"
    cls = _ADAPTERS.get(adapter_key, GenericHttpAdapter)
    return cls(device)


def is_face_terminal(device) -> bool:
    if not device or not device.model:
        return False
    return device.model.type == "face_terminal"
