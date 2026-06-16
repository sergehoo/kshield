"""Pilote LLRP pour portiques RFID UHF (FOCUS ST-G8 et compatibles).

Ouvre une session LLRP sur le port 5084 du portique, envoie un ROSpec qui
demande la lecture continue des tags, écoute les RO_ACCESS_REPORT, et pour
chaque EPC reçu :
  1. Lookup ``Badge`` par UID
  2. Crée un ``AccessEvent`` (decision granted/denied, direction selon checkpoint)
  3. Lookup ``Helmet`` par ``uhf_tag_uid`` → met à jour last_seen_at

À déployer en tant que **service longue durée** (1 process par portique) :
soit via Celery beat qui lance un poll court toutes les 10s, soit via un
container dédié exécutant ``manage.py run_uhf_gate <device_id>``.

Le module utilise une implémentation LLRP minimale (cf. scripts/llrp_inventory.py)
pour éviter la dépendance à sllurp qui est mal maintenu.
"""
from __future__ import annotations

import logging
import socket
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)


# Message types LLRP (cf. EPCglobal LLRP 1.1)
GET_READER_CAPABILITIES = 1
ADD_ROSPEC = 20
DELETE_ROSPEC = 21
START_ROSPEC = 22
STOP_ROSPEC = 23
ENABLE_ROSPEC = 24
DISABLE_ROSPEC = 25
SET_READER_CONFIG = 3
RO_ACCESS_REPORT = 61
READER_EVENT_NOTIFICATION = 63
KEEPALIVE = 62
KEEPALIVE_ACK = 72


def _hdr(msg_type: int, msg_id: int, length: int) -> bytes:
    ver_type = (1 << 10) | (msg_type & 0x3FF)
    return struct.pack(">HII", ver_type, length, msg_id)


def _parse_hdr(raw: bytes):
    if len(raw) < 10:
        return None, None, None
    ver_type, length, mid = struct.unpack(">HII", raw[:10])
    return ver_type & 0x3FF, length, mid


def _recv_msg(sock: socket.socket, timeout: float = 5.0):
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 10:
        chunk = sock.recv(10 - len(hdr))
        if not chunk:
            return None, None, None
        hdr += chunk
    mt, length, mid = _parse_hdr(hdr)
    body = b""
    remaining = length - 10
    while remaining > 0:
        chunk = sock.recv(min(remaining, 8192))
        if not chunk:
            return None, None, None
        body += chunk
        remaining -= len(chunk)
    return mt, mid, body


def _add_rospec(msg_id: int, duration_ms: int = 0) -> bytes:
    """ROSpec minimal : lecture continue sur toutes les antennes."""
    # Réutilise la même logique que scripts/llrp_inventory.py
    rospec_id = 1
    # NULL triggers (lecture continue)
    start_trigger = struct.pack(">HHB", 179, 5, 0)
    stop_trigger = struct.pack(">HHBI", 182, 9, 0, duration_ms)
    boundary = struct.pack(">HH", 178, 4 + len(start_trigger) + len(stop_trigger))
    boundary += start_trigger + stop_trigger
    # AISpec : toutes les antennes
    antennas = struct.pack(">HH", 1, 0)
    aispec_stop = struct.pack(">HHBI", 184, 9, 0, 0)
    inv_spec = struct.pack(">HHHB", 186, 7, 1, 1)
    aispec_body = antennas + aispec_stop + inv_spec
    aispec = struct.pack(">HH", 183, 4 + len(aispec_body)) + aispec_body
    # ROReportSpec : Upon_N_Tags_Or_End_Of_ROSpec
    tag_report = struct.pack(">HHH", 238, 6, 0)
    ror_body = struct.pack(">BH", 1, 1) + tag_report
    ror = struct.pack(">HH", 237, 4 + len(ror_body)) + ror_body
    body_inner = struct.pack(">IBB", rospec_id, 0, 0) + boundary + aispec + ror
    rospec_param = struct.pack(">HH", 177, 4 + len(body_inner)) + body_inner
    return _hdr(ADD_ROSPEC, msg_id, 10 + len(rospec_param)) + rospec_param


def _simple_msg(msg_type: int, msg_id: int, rospec_id: int = 1) -> bytes:
    return _hdr(msg_type, msg_id, 14) + struct.pack(">I", rospec_id)


def _parse_epcs(body: bytes) -> list[str]:
    """Extrait les EPC d'un RO_ACCESS_REPORT — version simplifiée."""
    epcs = []
    i = 0
    while i < len(body):
        if i + 4 > len(body):
            break
        first = body[i]
        if first & 0x80:
            ptype = first & 0x7F
            if ptype == 13 and i + 13 <= len(body):
                epcs.append(body[i + 1:i + 13].hex().upper())
                i += 13
            else:
                i += 1
        else:
            if i + 4 > len(body): break
            ptype, length = struct.unpack(">HH", body[i:i + 4])
            ptype &= 0x3FF
            if length < 4: break
            if ptype == 241 and i + 6 <= len(body):
                bit_len = struct.unpack(">H", body[i + 4:i + 6])[0]
                byte_len = (bit_len + 7) // 8
                epcs.append(body[i + 6:i + 6 + byte_len].hex().upper())
            i += length
    return epcs


class UhfGateClient:
    """Client LLRP pour un portique RFID UHF (FOCUS ST-G8 et autres)."""

    def __init__(self, ip: str, port: int = 5084, timeout: int = 5):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    def open(self):
        sock = socket.socket()
        sock.settimeout(self.timeout)
        sock.connect((self.ip, self.port))
        # Le portique envoie un READER_EVENT_NOTIFICATION à la connexion
        try:
            mt, _, _ = _recv_msg(sock, timeout=3.0)
        except socket.timeout:
            # Pas de notification spontanée → on provoque
            cap = struct.pack(">B", 0)
            sock.sendall(_hdr(GET_READER_CAPABILITIES, 1, 11) + cap)
            try:
                _recv_msg(sock, timeout=3.0)
            except Exception:
                pass
        self._sock = sock
        return self

    def close(self):
        if self._sock:
            try: self._sock.close()
            except Exception: pass
            self._sock = None

    def inventory(self, duration_seconds: int = 5) -> dict:
        """Lance un inventaire pendant `duration_seconds` et retourne les EPC vus.

        Returns:
            {"epcs": {"<EPC>": count, ...}, "duration": N}
        """
        if not self._sock:
            self.open()

        # Setup ROSpec
        self._sock.sendall(_simple_msg(DELETE_ROSPEC, 2, rospec_id=0))
        _recv_msg(self._sock, timeout=2.0)
        self._sock.sendall(_add_rospec(3))
        _recv_msg(self._sock, timeout=3.0)
        self._sock.sendall(_simple_msg(ENABLE_ROSPEC, 4))
        _recv_msg(self._sock, timeout=2.0)
        self._sock.sendall(_simple_msg(START_ROSPEC, 5))
        _recv_msg(self._sock, timeout=2.0)

        seen: dict[str, int] = {}
        deadline = time.time() + duration_seconds
        self._sock.settimeout(1.0)
        while time.time() < deadline:
            try:
                mt, mid, body = _recv_msg(self._sock, timeout=1.0)
            except socket.timeout:
                continue
            if mt is None:
                break
            if mt == RO_ACCESS_REPORT:
                for epc in _parse_epcs(body):
                    seen[epc] = seen.get(epc, 0) + 1
            elif mt == KEEPALIVE:
                try:
                    self._sock.sendall(_hdr(KEEPALIVE_ACK, mid, 10))
                except Exception:
                    pass

        # Cleanup
        try:
            self._sock.sendall(_simple_msg(STOP_ROSPEC, 99))
            _recv_msg(self._sock, timeout=2.0)
            self._sock.sendall(_simple_msg(DISABLE_ROSPEC, 100))
            _recv_msg(self._sock, timeout=2.0)
            self._sock.sendall(_simple_msg(DELETE_ROSPEC, 101))
            _recv_msg(self._sock, timeout=2.0)
        except Exception:
            pass

        return {"epcs": seen, "duration_seconds": duration_seconds}

    def __enter__(self): return self.open()
    def __exit__(self, *exc): self.close(); return False
