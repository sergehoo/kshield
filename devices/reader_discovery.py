"""KAYDAN SHIELD — Auto-discovery des lecteurs RFID UHF, NFC et beacons BLE.

Trois stratégies de découverte, combinables :

1. **mDNS / Bonjour** (lib ``zeroconf``) — découvre automatiquement les services
   publiés sur le LAN :
   - ``_llrp._tcp.local.``     → lecteurs RFID UHF (Impinj, Zebra, CAEN, Alien)
   - ``_pcsc._tcp.local.``     → lecteurs NFC réseau (HID OMNIKEY-IP, Sycreader)
   - ``_http._tcp.local.``     → gateways BLE (Aruba, Estimote, Kontakt.io)
2. **Scan TCP ciblé** sur un CIDR + ports caractéristiques (5084 LLRP, 80/443
   HTTP banner). Détecte les lecteurs qui ne publient pas en mDNS.
3. **HTTP banner probe** : récupère le header ``Server:`` et le titre HTML pour
   identifier la marque (Impinj Speedway, Zebra FX9600, Sycreader, etc.).

Dépendances optionnelles :
    pip install zeroconf

Sans cette dépendance, seul le scan TCP/HTTP fonctionne.

Usage :
    from devices.reader_discovery import discover_readers, ReaderDiscoveryUnavailable
    try:
        results = discover_readers(kind="uhf", cidr="192.168.1.0/24", timeout=5)
    except ReaderDiscoveryUnavailable as exc:
        # afficher message à l'utilisateur
        ...
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────
class ReaderDiscoveryError(RuntimeError):
    pass


class ReaderDiscoveryUnavailable(ReaderDiscoveryError):
    """Dépendances manquantes pour le mDNS."""


# ─────────────────────────────────────────────────────────────────────────────
# Constantes : ports / signatures
# ─────────────────────────────────────────────────────────────────────────────
#: Services mDNS par type de lecteur
_MDNS_SERVICES = {
    "uhf": ["_llrp._tcp.local.", "_impinj._tcp.local."],
    "nfc": ["_pcsc._tcp.local.", "_nfc._tcp.local."],
    "ble": ["_http._tcp.local."],  # gateways BLE exposent une API HTTP
    "zk":  ["_zkteco._tcp.local.", "_zk._tcp.local."],  # rare mais existe
}

#: Ports caractéristiques à scanner pour chaque techno
_TCP_PORTS = {
    "uhf": [5084, 5085, 80, 443, 22],   # LLRP + HTTP admin + SSH
    "nfc": [8000, 80, 443, 5577],       # HID/Sycreader HTTP + port custom
    "ble": [80, 443, 8080, 1883],       # gateway HTTP + MQTT
    "zk":  [4370, 4380, 80, 8081],      # ZKAccess SDK + ADMS push HTTP
}

#: Signatures HTTP → marque + modèle (Server header ou body contains)
_HTTP_SIGNATURES = {
    "uhf": [
        # (substring case-insensitive, brand, model_hint)
        ("impinj",        "Impinj",   "Speedway / R420"),
        ("speedway",      "Impinj",   "Speedway"),
        ("itemsense",     "Impinj",   "ItemSense"),
        ("zebra",         "Zebra",    "FX9600 / FX7500"),
        ("symbol fx",     "Zebra",    "FX series"),
        ("alien",         "Alien",    "ALR-9900+ / F800"),
        ("caen rfid",     "CAEN",     "Hadron / Ion / Lepton"),
        ("nordicid",      "Nordic ID","Sampo S2 / S3"),
        ("kathrein",      "Kathrein", "ARU 25xx / ARU 35xx"),
    ],
    "nfc": [
        ("omnikey",       "HID",      "OMNIKEY 5x27CK-IP"),
        ("hid global",    "HID",      "iCLASS SE"),
        ("sycreader",     "Sycreader","SYC-RFR300/400"),
        ("acr122",        "ACS",      "ACR122 IP gateway"),
        ("rfideas",       "RF IDeas", "pcProx Plus"),
    ],
    "ble": [
        ("aruba",         "Aruba",    "Meridian BLE gateway"),
        ("estimote",      "Estimote", "LTE Beacon"),
        ("kontakt",       "Kontakt.io", "Smart Beacon / Gateway"),
        ("minew",         "Minew",    "G1 / G2 gateway"),
        ("blukii",        "blukii",   "Sensor Beacon"),
    ],
    "zk": [
        ("zkteco",        "ZKTeco",   "Terminal pointage (K14/K20/F18/iClock…)"),
        ("anviz",         "Anviz",    "Terminal pointage"),
        ("zkaccess",      "ZKTeco",   "Terminal ZKAccess"),
    ],
}

#: Endpoints d'enrichissement par marque (renvoient souvent JSON ou HTML avec
#: modèle exact, firmware, n° série…). Tested in order.
_VENDOR_ENDPOINTS = {
    "Impinj": [
        "/cgi-bin/showStatus.cgi", "/cgi-bin/getReaderInfo.cgi",
        "/api/v1/system/info", "/admin.html",
    ],
    "Zebra": [
        "/getInformation.cgi", "/control/control.aspx",
        "/cgi-bin/system_info.cgi", "/api/system/info",
    ],
    "CAEN": ["/api/info", "/cgi-bin/info"],
    "Nordic ID": ["/api/info", "/system/info"],
    "Alien": ["/cmd/get/ReaderName", "/cmd/get/ReaderInfo"],
    "Kathrein": ["/api/v1/system", "/info"],
    "HID": ["/admin/system.xml", "/api/info"],
    "Sycreader": ["/api/info", "/system/info"],
    "Aruba": ["/api/v1/info", "/api/v1/configuration"],
    "Estimote": ["/api/v1/status"],
    "Kontakt.io": ["/api/v1/status", "/api/v1/info"],
    "Minew": ["/api/info", "/v1/info"],
    "_generic_": [
        "/api/info", "/api/v1/info", "/api/status", "/api/v1/status",
        "/system/info", "/system/info.json", "/info", "/status",
    ],
}

#: Patterns d'extraction de modèle/firmware/serial dans le texte récupéré
import re as _re
_MODEL_PATTERNS = [
    _re.compile(r'\b(R[0-9]{3,4}[A-Z]?)\b'),           # Impinj R420/R700
    _re.compile(r'\b(FX[0-9]{4})\b'),                   # Zebra FX9600/FX7500
    _re.compile(r'\b(ALR[-_ ]?[0-9]{3,4}[+]?)\b'),      # Alien ALR-9900+
    _re.compile(r'\b(ARU[-_ ]?[0-9]{4})\b'),            # Kathrein ARU 2400
    _re.compile(r'\b(Sampo[ _-]?S[0-9])\b', _re.I),     # Nordic ID Sampo S2/S3
    _re.compile(r'\b(OMNIKEY[ _-]?[0-9]{3,4}[A-Z]*)\b', _re.I),  # HID OMNIKEY
    _re.compile(r'"model"\s*:\s*"([^"]{2,60})"', _re.I),         # JSON "model"
    _re.compile(r'"modelName"\s*:\s*"([^"]{2,60})"', _re.I),
    _re.compile(r'"product"\s*:\s*"([^"]{2,60})"', _re.I),
]
_FIRMWARE_PATTERNS = [
    _re.compile(r'"firmware(?:Version|_version)?"\s*:\s*"([^"]{1,40})"', _re.I),
    _re.compile(r'"fw(?:Version)?"\s*:\s*"([^"]{1,40})"', _re.I),
    _re.compile(r'firmware[^a-z0-9]{0,5}((?:v|version[: ])?\s*[0-9][0-9a-z._-]{1,30})',
                _re.I),
]
_SERIAL_PATTERNS = [
    _re.compile(r'"serial(?:Number|_number)?"\s*:\s*"([^"]{3,40})"', _re.I),
    _re.compile(r'"sn"\s*:\s*"([^"]{3,40})"', _re.I),
    _re.compile(r'\b(?:serial\s*(?:number)?|s/n|sn)\s*[:#=]\s*([A-Z0-9._-]{6,30})\b',
                _re.I),
]
_MAC_PATTERN = _re.compile(
    r'\b((?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2})\b', _re.I)
_TITLE_PATTERN = _re.compile(r'<title[^>]*>([^<]{2,200})</title>', _re.I | _re.S)


# ─────────────────────────────────────────────────────────────────────────────
# mDNS discovery (zeroconf)
# ─────────────────────────────────────────────────────────────────────────────
def _discover_mdns(services: list[str], timeout: int = 5) -> list[dict]:
    """Découvre les services mDNS donnés et retourne une liste de dicts.

    Lève ``ReaderDiscoveryUnavailable`` si la lib zeroconf n'est pas installée.
    """
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError as exc:
        raise ReaderDiscoveryUnavailable(
            "Module 'zeroconf' non installé. Pour activer la découverte mDNS :\n"
            "    pip install zeroconf"
        ) from exc

    found: list[dict] = []
    lock = threading.Lock()

    class _Listener:
        def add_service(self, zc, type_, name):
            try:
                info = zc.get_service_info(type_, name, timeout=2000)
                if not info:
                    return
                ip = None
                try:
                    addrs = info.parsed_addresses()
                    if addrs:
                        ip = addrs[0]
                except Exception:
                    if info.addresses:
                        ip = ".".join(str(b) for b in info.addresses[0])
                props = {}
                try:
                    props = {
                        (k.decode() if isinstance(k, bytes) else k):
                        (v.decode() if isinstance(v, bytes) else v)
                        for k, v in (info.properties or {}).items() if k
                    }
                except Exception:
                    pass
                # Tente d'extraire modèle / firmware / MAC depuis les TXT records.
                # Les noms de clés courants : model, hw, hw_version, fw, fw_version,
                # firmware, sn, serial, mac, vendor, brand, mfg.
                def _prop(*keys):
                    for k in keys:
                        v = props.get(k) or props.get(k.lower()) or props.get(k.upper())
                        if v:
                            return str(v)[:80]
                    return None

                model_detected  = _prop("model", "Model", "product")
                firmware        = _prop("fw", "firmware", "fw_version", "fwVersion",
                                          "version")
                serial          = _prop("sn", "serial", "serialNumber", "serial_number")
                mac             = _prop("mac", "macAddress", "ethaddr", "ethernet")
                brand           = _prop("vendor", "brand", "mfg", "manufacturer")

                entry = {
                    "ip": ip,
                    "port": info.port,
                    "service": type_,
                    "name": (name.replace(type_, "").rstrip(".") or info.server or "Lecteur"),
                    "hostname": info.server,
                    "properties": props,
                    "via": "mdns",
                    "discovered_at": datetime.now().isoformat(timespec="seconds"),
                }
                if model_detected: entry["model_detected"] = model_detected
                if firmware:       entry["firmware_version"] = firmware
                if serial:         entry["serial_detected"] = serial
                if mac and _MAC_PATTERN.match(mac):
                    entry["mac_address"] = mac.upper().replace("-", ":")
                if brand:          entry["brand"] = brand

                with lock:
                    found.append(entry)
            except Exception as exc:
                logger.debug("mDNS get_service_info failed for %s: %s", name, exc)

        def remove_service(self, zc, type_, name): pass
        def update_service(self, zc, type_, name): pass

    zc = Zeroconf()
    try:
        browsers = [ServiceBrowser(zc, svc, _Listener()) for svc in services]
        # Laisse remonter les annonces
        import time as _time
        _time.sleep(min(max(timeout, 2), 15))
        for b in browsers:
            try: b.cancel()
            except Exception: pass
    finally:
        try: zc.close()
        except Exception: pass

    # Déduplique sur (ip, port)
    seen = set()
    deduped = []
    for r in found:
        key = (r.get("ip"), r.get("port"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


# ─────────────────────────────────────────────────────────────────────────────
# Scan TCP + HTTP banner probe
# ─────────────────────────────────────────────────────────────────────────────
def _tcp_open(ip: str, port: int, timeout: float = 0.5) -> bool:
    """Test ouverture port TCP — non-bloquant."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((ip, port)) == 0
    except Exception:
        return False


def _http_get(url: str, timeout: float = 1.5,
              max_bytes: int = 16384) -> Optional[tuple[dict, str]]:
    """GET HTTP avec verify SSL off. Retourne (headers_dict, body_text) ou None.

    ``max_bytes`` cape la lecture pour éviter de pomper sur un mauvais target.
    """
    import ssl
    import urllib.request
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "KaydanShield-Discovery/1.0"},
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            headers = dict(resp.headers.items())
            body = resp.read(max_bytes).decode(errors="ignore")
            return headers, body
    except Exception as exc:
        logger.debug("HTTP GET %s failed: %s", url, exc)
        return None


def _extract_info(haystack: str, info: dict) -> None:
    """Extrait modèle / firmware / serial / MAC depuis du texte HTML ou JSON.

    Mute ``info`` en place — n'écrase pas une valeur déjà présente.
    """
    # Modèle exact (regex prioritaires)
    if not info.get("model_detected"):
        for pat in _MODEL_PATTERNS:
            m = pat.search(haystack)
            if m:
                val = m.group(1).strip()
                if 2 < len(val) < 60:
                    info["model_detected"] = val
                    break
    # Firmware
    if not info.get("firmware_version"):
        for pat in _FIRMWARE_PATTERNS:
            m = pat.search(haystack)
            if m:
                info["firmware_version"] = m.group(1).strip()[:40]
                break
    # Serial
    if not info.get("serial_detected"):
        for pat in _SERIAL_PATTERNS:
            m = pat.search(haystack)
            if m:
                val = m.group(1).strip()
                if 3 < len(val) < 40 and val.lower() != "null":
                    info["serial_detected"] = val
                    break
    # MAC address (dans le body — beaucoup d'admins l'affichent)
    if not info.get("mac_address"):
        m = _MAC_PATTERN.search(haystack)
        if m:
            mac = m.group(1).upper().replace("-", ":")
            # Exclut le MAC bidon 00:00:00:00:00:00
            if mac != "00:00:00:00:00:00":
                info["mac_address"] = mac
    # Titre HTML (utile comme fallback de modèle)
    if not info.get("title"):
        t = _TITLE_PATTERN.search(haystack)
        if t:
            title = _re.sub(r"\s+", " ", t.group(1)).strip()
            if 2 < len(title) < 200:
                info["title"] = title


def _enrich_via_endpoints(ip: str, port: int, brand: str,
                          timeout: float = 1.0) -> dict:
    """Interroge les endpoints connus de la marque pour récupérer modèle/firmware/SN.

    Retourne un dict avec les clés trouvées (``model_detected``, ``firmware_version``,
    ``serial_detected``, ``mac_address``, ``title``, ``endpoints_tried``).
    """
    scheme = "https" if port in (443, 8443) else "http"
    base = f"{scheme}://{ip}:{port}"
    paths = list(_VENDOR_ENDPOINTS.get(brand, []))
    paths += [p for p in _VENDOR_ENDPOINTS["_generic_"] if p not in paths]

    info: dict = {"endpoints_tried": []}
    for path in paths[:6]:   # cap à 6 tentatives — au-delà c'est du gaspillage
        url = base + path
        res = _http_get(url, timeout=timeout, max_bytes=16384)
        info["endpoints_tried"].append(path)
        if not res:
            continue
        headers, body = res
        _extract_info(body, info)
        # Si on a déjà tout ce qu'on cherchait, on arrête
        if (info.get("model_detected") and info.get("firmware_version")
                and info.get("serial_detected")):
            break
    return info


def _get_mac_from_arp(ip: str) -> Optional[str]:
    """Cherche le MAC associé à une IP dans la table ARP du kernel.

    Marche sur Linux (parse /proc/net/arp). Retourne None ailleurs ou si pas trouvé.
    """
    try:
        with open("/proc/net/arp", "r") as f:
            lines = f.readlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4 and parts[0] == ip:
                mac = parts[3].upper()
                if mac and mac != "00:00:00:00:00:00":
                    return mac
    except Exception:
        pass
    return None


def _http_probe(ip: str, port: int, kind: str, timeout: float = 1.5) -> Optional[dict]:
    """Tente HTTP GET / + enrichissement, identifie marque + modèle + firmware + SN.

    Retourne ``None`` si pas de match HTTP du tout.
    """
    scheme = "https" if port in (443, 8443) else "http"
    url = f"{scheme}://{ip}:{port}/"
    res = _http_get(url, timeout=timeout, max_bytes=8192)
    if not res:
        return None
    headers, body = res
    server = (headers.get("Server") or "").lower()
    haystack = server + " | " + body.lower()

    brand = None
    model_hint = None
    for substring, b, mh in _HTTP_SIGNATURES.get(kind, []):
        if substring.lower() in haystack:
            brand = b
            model_hint = mh
            break

    out: dict = {
        "url": url,
        "server_header": headers.get("Server", ""),
        "brand": brand or "Inconnu",
        "model_hint": model_hint or (headers.get("Server", "") or "?"),
    }
    # Extraction des infos de la home page (titre, MAC parfois visible, etc.)
    _extract_info(body, out)
    # Enrichissement via endpoints connus si on a identifié une marque
    if brand:
        enriched = _enrich_via_endpoints(ip, port, brand, timeout=timeout * 0.7)
        # Merge sans écraser ce qu'on a déjà
        for k, v in enriched.items():
            if k == "endpoints_tried":
                out["endpoints_tried"] = v
            elif v and not out.get(k):
                out[k] = v
    return out


def _scan_host(ip: str, kind: str, timeout: float = 0.5) -> Optional[dict]:
    """Scan TCP + HTTP probe + enrichissement sur un hôte. Retourne dict ou None."""
    ports = _TCP_PORTS.get(kind, [])
    open_ports = [p for p in ports if _tcp_open(ip, p, timeout=timeout)]
    if not open_ports:
        return None

    # Pour UHF : port 5084 ouvert = LLRP très probable
    is_llrp = (kind == "uhf" and 5084 in open_ports)

    # HTTP probe + enrichissement multi-endpoints sur le 1er port HTTP trouvé
    http_info = None
    for p in (80, 443, 8080, 8000):
        if p in open_ports:
            http_info = _http_probe(ip, p, kind, timeout=max(timeout * 3, 1.5))
            if http_info:
                break

    entry = {
        "ip": ip,
        "open_ports": open_ports,
        "via": "tcp_scan",
        "discovered_at": datetime.now().isoformat(timespec="seconds"),
    }
    if is_llrp:
        entry["protocol"] = "LLRP"
        entry["port"] = 5084
    if http_info:
        # Copie toutes les clés trouvées par l'enrichissement
        for k in ("brand", "model_hint", "model_detected", "firmware_version",
                  "serial_detected", "mac_address", "title", "url",
                  "server_header", "endpoints_tried"):
            v = http_info.get(k)
            if v:
                entry[k] = v
    if "brand" not in entry:
        entry["brand"] = "Inconnu"
        entry["model_hint"] = f"Ports ouverts : {','.join(str(p) for p in open_ports)}"

    # Probe ZKAccess SDK (port 4370) — récupère firmware, serial, nom
    # depuis le terminal directement. Beaucoup plus fiable qu'un HTTP probe
    # car les ZKTeco n'exposent souvent pas d'admin web.
    if any(p == 4370 for p in open_ports):
        try:
            from .zk_client import ZkClient, ZkConnectionError, ZkUnavailable
            try:
                with ZkClient(ip, port=4370, timeout=3).open() as zk:
                    zk_info = zk.info()
            except (ZkUnavailable, ZkConnectionError):
                zk_info = None
            if zk_info:
                # ZKTeco identifié sans ambiguïté
                entry["brand"] = "ZKTeco"
                entry["protocol"] = "ZKAccess SDK"
                entry["port"] = 4370
                if zk_info.get("name"):       entry["model_detected"] = zk_info["name"]
                if zk_info.get("firmware"):   entry["firmware_version"] = zk_info["firmware"]
                if zk_info.get("serial"):     entry["serial_detected"] = zk_info["serial"]
                if zk_info.get("mac"):        entry["mac_address"] = zk_info["mac"]
                if zk_info.get("platform"):   entry["platform"] = zk_info["platform"]
                entry["users_count"] = zk_info.get("users_count")
                entry["fingerprints_count"] = zk_info.get("fingerprints_count")
        except Exception as exc:
            logger.debug("ZK probe %s failed: %s", ip, exc)

    # Fallback MAC via cache ARP du kernel (Linux uniquement)
    if not entry.get("mac_address"):
        mac = _get_mac_from_arp(ip)
        if mac:
            entry["mac_address"] = mac
            entry["mac_source"] = "arp"
    return entry


def _scan_cidr(cidr: str, kind: str, timeout: float = 0.5,
               max_workers: int = 64) -> list[dict]:
    """Scan parallèle d'un CIDR. Limite : 4096 IPs (un /20)."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ReaderDiscoveryError(f"CIDR invalide : {cidr} ({exc})") from exc
    if net.num_addresses > 4096:
        raise ReaderDiscoveryError(
            f"CIDR trop large ({net.num_addresses} adresses). "
            f"Limite : /20 (4096 hôtes max). Affinez la plage."
        )

    hosts = [str(h) for h in net.hosts()]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_scan_host, h, kind, timeout): h for h in hosts}
        for fut in as_completed(futures):
            try:
                r = fut.result()
                if r:
                    results.append(r)
            except Exception as exc:
                logger.debug("scan_host failed: %s", exc)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée public
# ─────────────────────────────────────────────────────────────────────────────
def discover_readers(kind: str, cidr: Optional[str] = None,
                     timeout: int = 5, mdns: bool = True) -> list[dict]:
    """Découvre les lecteurs sur le LAN.

    Args:
        kind: ``"uhf"``, ``"nfc"`` ou ``"ble"``.
        cidr: plage CIDR à scanner en TCP (ex. ``"192.168.1.0/24"``). Optionnel.
              Sans CIDR, seul le mDNS est utilisé.
        timeout: durée du scan en secondes (3 à 15 conseillé).
        mdns: si False, désactive la découverte mDNS.

    Returns:
        Liste de dicts :
            {
                "ip":           "192.168.1.50",
                "port":         5084,                # si connu
                "brand":        "Impinj",
                "model_hint":   "Speedway R420",
                "protocol":     "LLRP",              # UHF uniquement
                "open_ports":   [22, 80, 5084],
                "url":          "http://192.168.1.50/", # si HTTP probe a abouti
                "name":         "speedway-1.local",
                "via":          "mdns" | "tcp_scan",
                "discovered_at": "2026-06-08T15:30:00",
            }

    Raises:
        ReaderDiscoveryError pour erreurs de paramètres (CIDR invalide).
        ReaderDiscoveryUnavailable si mDNS demandé mais zeroconf manquant
          ET pas de CIDR fourni en fallback.
    """
    kind = (kind or "").lower()
    if kind not in _MDNS_SERVICES:
        raise ReaderDiscoveryError(
            f"Type de lecteur inconnu : {kind!r} (attendu : uhf, nfc, ble)"
        )

    results: list[dict] = []
    mdns_error: Optional[str] = None

    # 1. mDNS
    if mdns:
        try:
            results.extend(_discover_mdns(_MDNS_SERVICES[kind], timeout=timeout))
        except ReaderDiscoveryUnavailable as exc:
            mdns_error = str(exc)
            if not cidr:
                # Pas de fallback possible → on lève
                raise
        except Exception as exc:
            logger.warning("mDNS discovery failed: %s", exc)
            mdns_error = str(exc)

    # 2. Scan TCP du CIDR si fourni
    if cidr:
        per_host_timeout = max(0.3, min(timeout / 12.0, 1.5))
        tcp_results = _scan_cidr(cidr, kind, timeout=per_host_timeout)
        # Merge : si une IP est déjà dans `results` (via mDNS), on enrichit
        by_ip = {r.get("ip"): r for r in results if r.get("ip")}
        for r in tcp_results:
            ip = r.get("ip")
            if ip in by_ip:
                existing = by_ip[ip]
                # Complète mais n'écrase pas ce que mDNS a déjà fourni
                for k in ("open_ports", "model_detected", "firmware_version",
                          "serial_detected", "mac_address", "title", "url",
                          "server_header", "endpoints_tried", "protocol",
                          "model_hint"):
                    if r.get(k) and not existing.get(k):
                        existing[k] = r[k]
                # brand : si mDNS a "Inconnu", TCP peut surclasser
                if r.get("brand") and (
                    not existing.get("brand") or existing.get("brand") == "Inconnu"
                ):
                    existing["brand"] = r["brand"]
            else:
                results.append(r)

    # Décore avec un message d'erreur partiel si mDNS a planté mais TCP a sauvé
    if mdns_error and not mdns:
        # mDNS désactivé volontairement, on n'expose pas l'erreur
        pass
    return results
