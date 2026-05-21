"""KAYDAN SHIELD — Probe RTSP : devine l'URL d'une caméra à partir de l'IP.

Deux stratégies en cascade :

1. **ONVIF GetStreamUri** (haut niveau, le plus fiable)
   - Connecte au service ONVIF de la caméra (port 80/8000) avec credentials.
   - Récupère le `StreamUri` du premier profile média = URL RTSP officielle.

2. **Dictionnaire de chemins RTSP constructeurs** (fallback)
   - Liste exhaustive des chemins RTSP connus pour HikVision, Dahua, Axis,
     Hanwha (Samsung), Bosch, Reolink, Tapo, Foscam, Vivotek, Uniview…
   - On essaie chaque URL avec OpenCV (timeout 4s). Première qui s'ouvre = OK.

Usage :

    from devices.rtsp_probe import probe_rtsp
    url, brand, error = probe_rtsp("192.168.1.50", "admin", "azerty123")
    if url:
        cam.rtsp_url = url
        cam.save()
    else:
        print(f"Échec : {error}")
"""
from __future__ import annotations

import logging
import socket
import time
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dictionnaire de chemins RTSP par constructeur
# ---------------------------------------------------------------------------
# Chaque entrée = (brand, path) — `path` peut contenir %CH% (numéro de canal,
# par défaut 1) et %ST% (stream : 0=main, 1=sub).
# L'ordre détermine la priorité : main streams haute qualité d'abord.

RTSP_PATHS: list[tuple[str, str]] = [
    # ─── HikVision (et OEM : Annke, LaView, Swann) ───
    ("hikvision", "/Streaming/Channels/%CH%01"),     # main
    ("hikvision", "/Streaming/Channels/%CH%02"),     # sub
    ("hikvision", "/h264/ch%CH%/main/av_stream"),    # ancien firmware
    ("hikvision", "/h264/ch%CH%/sub/av_stream"),

    # ─── Dahua (et OEM : Amcrest, Lorex, EmpireTech) ───
    ("dahua", "/cam/realmonitor?channel=%CH%&subtype=0"),  # main
    ("dahua", "/cam/realmonitor?channel=%CH%&subtype=1"),  # sub

    # ─── Axis (Profile 1 = main, Profile 2 = sub) ───
    ("axis", "/axis-media/media.amp?streamprofile=Quality"),
    ("axis", "/axis-media/media.amp"),
    ("axis", "/onvif-media/media.amp"),

    # ─── Hanwha / Samsung (Wisenet) ───
    ("hanwha", "/profile2/media.smp"),
    ("hanwha", "/profile1/media.smp"),
    ("hanwha", "/onvif/profile2/media.smp"),

    # ─── Bosch (IP Dinion, Flexidome) ───
    ("bosch", "/rtsp_tunnel"),
    ("bosch", "/?h26x=4&line=1&inst=1"),

    # ─── Reolink (E1, RLC, Argus) ───
    ("reolink", "/h264Preview_0%CH%_main"),
    ("reolink", "/h264Preview_0%CH%_sub"),
    ("reolink", "/Preview_0%CH%_main"),

    # ─── TP-Link Tapo (C100, C200, C310, C500) ───
    ("tplink_tapo", "/stream1"),  # main
    ("tplink_tapo", "/stream2"),  # sub

    # ─── Foscam (FI / SD / R / G series) ───
    ("foscam", "/videoMain"),
    ("foscam", "/videoSub"),
    ("foscam", "/video.cgi?stream=0"),

    # ─── Vivotek ───
    ("vivotek", "/live.sdp"),
    ("vivotek", "/live2.sdp"),

    # ─── Uniview (Uniarch) ───
    ("uniview", "/media/video1"),
    ("uniview", "/media/video2"),

    # ─── Mobotix ───
    ("mobotix", "/mobotix.sdp"),
    ("mobotix", "/cgi-bin/faststream.jpg?stream=full"),  # MJPEG fallback

    # ─── Pelco (Sarix, Spectra) ───
    ("pelco", "/stream1"),
    ("pelco", "/stream2"),

    # ─── D-Link (DCS series) ───
    ("dlink", "/live1.sdp"),
    ("dlink", "/play1.sdp"),

    # ─── Sony (SNC) ───
    ("sony", "/video1"),
    ("sony", "/media/video1"),

    # ─── Generic ONVIF (souvent supporté par les NoName chinois) ───
    ("generic", "/live"),
    ("generic", "/live.sdp"),
    ("generic", "/h264"),
    ("generic", "/stream"),
    ("generic", "/main"),
    ("generic", "/video.h264"),
    ("generic", "/0"),
    ("generic", "/1"),

    # ─── Caméras IP Wansview / Sricam / EZVIZ low-cost ───
    ("wansview", "/live/ch00_0"),
    ("wansview", "/live/ch00_1"),
    ("sricam", "/onvif1"),
    ("ezviz", "/Streaming/Channels/1"),
]


def _build_url(host: str, port: int, user: str, password: str,
               path: str, channel: int = 1) -> str:
    """Construit l'URL RTSP complète avec credentials encodés."""
    creds = ""
    if user:
        u = quote(user, safe="")
        p = quote(password, safe="")
        creds = f"{u}:{p}@"
    # Substitution paramètres
    path = path.replace("%CH%", str(channel))
    if not path.startswith("/"):
        path = "/" + path
    return f"rtsp://{creds}{host}:{port}{path}"


# ---------------------------------------------------------------------------
# Tests de connectivité bas niveau
# ---------------------------------------------------------------------------
def _tcp_alive(host: str, port: int, timeout: float = 2.0) -> bool:
    """Teste si le port TCP est ouvert (avant de tenter RTSP)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _try_open_rtsp(url: str, timeout_sec: float = 4.0) -> bool:
    """Tente d'ouvrir l'URL RTSP avec OpenCV. True si une frame est lue."""
    try:
        import cv2
        import os
    except ImportError:
        logger.warning("OpenCV indisponible — probe RTSP désactivé.")
        return False

    # Options FFmpeg : timeout 4s, TCP forcé (plus fiable que UDP en LAN)
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp|stimeout;{int(timeout_sec * 1_000_000)}|"
        f"max_delay;500000|reconnect;0"
    )
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap or not cap.isOpened():
        try:
            cap.release()
        except Exception:
            pass
        return False
    start = time.time()
    ok = False
    try:
        while time.time() - start < timeout_sec:
            ret, frame = cap.read()
            if ret and frame is not None:
                ok = True
                break
            time.sleep(0.1)
    finally:
        try:
            cap.release()
        except Exception:
            pass
    return ok


# ---------------------------------------------------------------------------
# ONVIF probe (méthode principale)
# ---------------------------------------------------------------------------
def _probe_via_onvif(host: str, user: str, password: str,
                     port: int = 80) -> Optional[str]:
    """Interroge ONVIF GetStreamUri. Retourne l'URL RTSP officielle ou None."""
    try:
        from onvif import ONVIFCamera
    except ImportError:
        logger.debug("onvif-zeep non installé — skip ONVIF probe.")
        return None

    # On essaie les ports ONVIF habituels dans l'ordre
    candidate_ports = [port, 80, 8000, 8080, 2020, 8899]
    seen = set()
    for p in candidate_ports:
        if p in seen:
            continue
        seen.add(p)
        if not _tcp_alive(host, p, timeout=1.5):
            continue
        try:
            cam = ONVIFCamera(host=host, port=p, user=user, passwd=password)
            media = cam.create_media_service()
            profiles = media.GetProfiles()
            if not profiles:
                continue
            req = media.create_type("GetStreamUri")
            req.ProfileToken = profiles[0].token
            req.StreamSetup = {"Stream": "RTP-Unicast",
                                "Transport": {"Protocol": "RTSP"}}
            stream = media.GetStreamUri(req)
            uri = getattr(stream, "Uri", None)
            if uri:
                # Beaucoup de caméras renvoient l'URL SANS les creds —
                # on les ré-injecte pour que ce soit directement utilisable
                if user and "@" not in uri:
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(uri)
                    creds = f"{quote(user, safe='')}:{quote(password, safe='')}"
                    netloc = f"{creds}@{parsed.hostname}"
                    if parsed.port:
                        netloc += f":{parsed.port}"
                    uri = urlunparse(parsed._replace(netloc=netloc))
                logger.info("ONVIF GetStreamUri OK pour %s:%d → %s",
                             host, p, uri.split("@")[-1])
                return uri
        except Exception as exc:
            logger.debug("ONVIF probe %s:%d échec : %s", host, p, exc)
            continue
    return None


# ---------------------------------------------------------------------------
# Probe principale (entrée publique)
# ---------------------------------------------------------------------------
def probe_rtsp(host: str, user: str = "", password: str = "",
               rtsp_port: int = 554, onvif_port: int = 80,
               channel: int = 1, fast_mode: bool = False
               ) -> tuple[Optional[str], Optional[str], str]:
    """Devine l'URL RTSP d'une caméra à partir de son IP.

    Args:
        host: IP ou hostname de la caméra (ex: "192.168.1.50").
        user: login admin caméra (ex: "admin").
        password: mot de passe.
        rtsp_port: port RTSP (par défaut 554).
        onvif_port: port ONVIF probable (par défaut 80, parfois 8000).
        channel: numéro de canal pour les NVR multi-canaux (1 par défaut).
        fast_mode: si True, on stoppe au premier hit (pas d'enumeration brand).

    Returns:
        (rtsp_url, brand, error_message)
        - rtsp_url : URL complète prête pour cv2.VideoCapture, ou None
        - brand    : "hikvision" / "dahua" / ... ou None
        - error_message : "" si OK, sinon raison de l'échec
    """
    if not host:
        return None, None, "IP / hostname manquant."

    # ─── 1. Sanity check TCP RTSP ─────────────────────────────────────
    if not _tcp_alive(host, rtsp_port, timeout=2.0):
        return (None, None,
                f"Le port RTSP {rtsp_port} de {host} ne répond pas. "
                f"Vérifie le câble réseau, l'IP et le pare-feu.")

    # ─── 2. Tentative ONVIF (la meilleure méthode) ────────────────────
    logger.info("Probe ONVIF de %s…", host)
    onvif_url = _probe_via_onvif(host, user, password, port=onvif_port)
    if onvif_url:
        if _try_open_rtsp(onvif_url, timeout_sec=5.0):
            return onvif_url, "onvif", ""
        logger.info("ONVIF a renvoyé une URL mais elle ne s'ouvre pas, "
                     "fallback dictionnaire de chemins.")

    # ─── 3. Fallback : dictionnaire de chemins constructeurs ──────────
    logger.info("Probe RTSP par dictionnaire pour %s…", host)
    tried = []
    for brand, path in RTSP_PATHS:
        url = _build_url(host, rtsp_port, user, password, path, channel=channel)
        tried.append((brand, path))
        if _try_open_rtsp(url, timeout_sec=3.5):
            logger.info("RTSP OK : marque détectée = %s, path = %s", brand, path)
            return url, brand, ""
        if fast_mode and len(tried) >= 6:
            break

    return (None, None,
            "Aucun chemin RTSP n'a fonctionné. Vérifie les identifiants "
            "(login/mot de passe). Marques testées : "
            + ", ".join(sorted({b for b, _ in tried})))


def probe_multiple_ips(ips: list[str], user: str = "", password: str = "",
                        ) -> list[dict]:
    """Probe en parallèle une liste d'IP. Retourne le résultat par IP."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    with ThreadPoolExecutor(max_workers=min(len(ips), 8)) as pool:
        futures = {
            pool.submit(probe_rtsp, ip, user, password, fast_mode=True): ip
            for ip in ips
        }
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                url, brand, err = fut.result()
                results.append({
                    "ip": ip, "rtsp_url": url,
                    "brand": brand, "error": err, "ok": url is not None,
                })
            except Exception as exc:
                results.append({
                    "ip": ip, "rtsp_url": None,
                    "brand": None, "error": str(exc), "ok": False,
                })
    # Trie pour mettre les succès en haut
    results.sort(key=lambda r: (not r["ok"], r["ip"]))
    return results
