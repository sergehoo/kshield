"""KAYDAN SHIELD — Auto-discovery ONVIF de caméras IP sur le LAN.

Utilise WS-Discovery (multicast 239.255.255.250:3702) pour découvrir les
caméras compatibles ONVIF sur le réseau local. Pour chaque caméra trouvée :

- Récupère le profile principal (StreamUri RTSP).
- Lit nom, modèle, adresse IP, MAC (si dispo via NetworkInterfaces).
- Retourne une liste de dict prêts à pré-remplir le formulaire Camera.

Dépendances optionnelles (non installées par défaut) :
    pip install wsdiscovery onvif-zeep

Si non installées, ``discover_cameras()`` lève ``OnvifUnavailable`` avec
des instructions claires.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OnvifError(RuntimeError):
    pass


class OnvifUnavailable(OnvifError):
    """Bibliothèques ONVIF non installées."""


def discover_cameras(timeout: int = 5,
                       fetch_streams: bool = True,
                       credentials: Optional[dict] = None) -> list[dict]:
    """Découvre les caméras ONVIF sur le LAN.

    Args:
        timeout: durée du multicast WS-Discovery en secondes (3-10 recommandé).
        fetch_streams: si True, tente de récupérer le StreamUri RTSP via ONVIF
            (nécessite credentials ou caméra ouverte).
        credentials: dict ``{"user": "admin", "pass": "..."}`` pour le test
            StreamUri. Optionnel — sans credentials, fetch_streams renverra
            l'XAddr ONVIF mais pas la RTSP URL.

    Returns:
        Liste de dicts :
            {
                "name":      "HikVision DS-2CD2143G0",
                "ip":        "192.168.1.50",
                "xaddr":     "http://192.168.1.50/onvif/device_service",
                "rtsp_url":  "rtsp://admin:****@192.168.1.50:554/...",  # si dispo
                "scopes":    [...],
                "manufacturer": "HikVision",
                "model":     "DS-2CD2143G0",
                "serial":    "...",
                "discovered_at": "2026-05-11T...",
            }

    Raises:
        OnvifUnavailable si wsdiscovery / onvif-zeep manquent.
        OnvifError pour les autres erreurs.
    """
    try:
        from wsdiscovery import QName
        from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
    except ImportError as exc:
        raise OnvifUnavailable(
            "Bibliothèques manquantes. Installer :\n"
            "    pip install wsdiscovery onvif-zeep"
        ) from exc

    from datetime import datetime
    from urllib.parse import urlparse

    wsd = WSDiscovery()
    wsd.start()
    try:
        # Recherche WS-Discovery — type spécifique aux caméras NetworkVideoTransmitter
        type_q = QName(
            "http://www.onvif.org/ver10/network/wsdl", "NetworkVideoTransmitter"
        )
        services = wsd.searchServices(types=[type_q], timeout=timeout)
        logger.info("WS-Discovery → %d service(s) trouvé(s)", len(services))
    finally:
        wsd.stop()

    results = []
    for svc in services:
        try:
            xaddrs = list(svc.getXAddrs() or [])
            scopes = [str(s) for s in (svc.getScopes() or [])]
            xaddr = xaddrs[0] if xaddrs else ""
            parsed = urlparse(xaddr) if xaddr else None
            ip = parsed.hostname if parsed else None

            entry = {
                "name":         _scope_value(scopes, "name", default="Caméra ONVIF"),
                "ip":           ip,
                "xaddr":        xaddr,
                "scopes":       scopes,
                "manufacturer": _scope_value(scopes, "hardware", default=""),
                "model":        _scope_value(scopes, "type", default=""),
                "serial":       None,
                "rtsp_url":     None,
                "discovered_at": datetime.now().isoformat(),
            }

            # Enrichissement via ONVIF (Device + Media services)
            if fetch_streams and ip and credentials:
                try:
                    entry.update(_fetch_onvif_details(xaddr, credentials))
                except Exception as exc:
                    logger.debug("Camera %s: ONVIF details fail: %s", ip, exc)
                    entry["onvif_error"] = str(exc)

            results.append(entry)
        except Exception as exc:
            logger.warning("WS-Discovery parse fail: %s", exc, exc_info=True)
    return results


def _scope_value(scopes: list, key: str, default: str = "") -> str:
    """Extrait une valeur scope ONVIF du format ``onvif://www.onvif.org/<key>/<value>``."""
    prefix = f"onvif://www.onvif.org/{key}/"
    for s in scopes:
        if s.startswith(prefix):
            from urllib.parse import unquote
            return unquote(s[len(prefix):])
    return default


def _fetch_onvif_details(xaddr: str, credentials: dict) -> dict:
    """Interroge la caméra via ONVIF pour récupérer modèle/serial/RTSP URL."""
    try:
        from onvif import ONVIFCamera
    except ImportError:
        return {}

    from urllib.parse import urlparse
    p = urlparse(xaddr)
    cam = ONVIFCamera(
        host=p.hostname, port=p.port or 80,
        user=credentials["user"], passwd=credentials["pass"],
    )
    info = cam.devicemgmt.GetDeviceInformation()
    out = {
        "manufacturer": getattr(info, "Manufacturer", None),
        "model":        getattr(info, "Model", None),
        "firmware":     getattr(info, "FirmwareVersion", None),
        "serial":       getattr(info, "SerialNumber", None),
    }

    # Récupération du StreamUri du premier profile média
    try:
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        if profiles:
            req = media.create_type("GetStreamUri")
            req.ProfileToken = profiles[0].token
            req.StreamSetup = {"Stream": "RTP-Unicast",
                                "Transport": {"Protocol": "RTSP"}}
            stream = media.GetStreamUri(req)
            out["rtsp_url"] = getattr(stream, "Uri", None)
    except Exception as exc:
        logger.debug("GetStreamUri fail: %s", exc)

    return out
