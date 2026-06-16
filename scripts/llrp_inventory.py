#!/usr/bin/env python3
"""LLRP inventory minimal — pure Python (pas de dépendance externe).

Usage :
    python scripts/llrp_inventory.py <ip> [duration_seconds]
    python scripts/llrp_inventory.py 10.20.1.66 5

Le script :
  1. Se connecte au port 5084 du lecteur,
  2. Attend le READER_EVENT_NOTIFICATION initial (le lecteur est prêt),
  3. Envoie un ADD_ROSPEC minimal (lecture continue),
  4. ENABLE_ROSPEC + START_ROSPEC,
  5. Lit les RO_ACCESS_REPORT pendant `duration_seconds`,
  6. Parse les EPC (paramètre 13 ou 241) et les affiche.

Conforme à la spec LLRP 1.1 (EPCglobal).
"""
import socket
import struct
import sys
import time


# Message types LLRP
GET_READER_CAPABILITIES        = 1
GET_READER_CAPABILITIES_RESPONSE = 11
ADD_ROSPEC                     = 20
DELETE_ROSPEC                  = 21
START_ROSPEC                   = 22
STOP_ROSPEC                    = 23
ENABLE_ROSPEC                  = 24
DISABLE_ROSPEC                 = 25
SET_READER_CONFIG              = 3
SET_READER_CONFIG_RESPONSE     = 13
RO_ACCESS_REPORT               = 61
READER_EVENT_NOTIFICATION      = 63
KEEPALIVE                      = 62
KEEPALIVE_ACK                  = 72


def llrp_header(msg_type: int, msg_id: int, length: int) -> bytes:
    """Header LLRP : 6 octets (version=1, type, length, msg_id)."""
    ver_type = (1 << 10) | (msg_type & 0x3FF)
    return struct.pack(">HII", ver_type, length, msg_id)


def parse_header(raw: bytes):
    if len(raw) < 10:
        return None, None, None
    ver_type, length, msg_id = struct.unpack(">HII", raw[:10])
    msg_type = ver_type & 0x3FF
    return msg_type, length, msg_id


def recv_message(sock: socket.socket, timeout: float = 5.0):
    """Reçoit un message LLRP complet (header + body)."""
    sock.settimeout(timeout)
    hdr = b""
    while len(hdr) < 10:
        chunk = sock.recv(10 - len(hdr))
        if not chunk:
            return None, None, None
        hdr += chunk
    msg_type, length, msg_id = parse_header(hdr)
    body = b""
    remaining = length - 10
    while remaining > 0:
        chunk = sock.recv(min(remaining, 8192))
        if not chunk:
            return None, None, None
        body += chunk
        remaining -= len(chunk)
    return msg_type, msg_id, body


def build_set_reader_config_reset(msg_id: int) -> bytes:
    """SET_READER_CONFIG avec ResetToFactoryDefaults=1 (R<<7=0x80)."""
    body = bytes([0x80])  # reset_to_factory_default
    return llrp_header(SET_READER_CONFIG, msg_id, 10 + len(body)) + body


def build_add_rospec(msg_id: int) -> bytes:
    """ROSpec minimal : lecture continue de toutes les antennes."""
    # ROSpec parameter (177)
    #   ROSpecID (4) + Priority (1) + CurrentState (1) + ROBoundarySpec + AISpec + ROReportSpec
    rospec_id = 1
    priority = 0
    current_state = 0   # disabled
    # ROBoundarySpec (178) :
    #   ROSpecStartTrigger (179) type=0 (null), ROSpecStopTrigger (182) type=0 (null)
    ro_start = struct.pack(">HHB", 179, 1+2+2, 0) + b""   # placeholder
    # plus simple : null triggers (TLV minimal)
    # ROSpecStartTrigger : type=0 (Null)
    start_trigger = struct.pack(">HHB", 179, 5, 0)
    # ROSpecStopTrigger : type=0 (Null), DurationTriggerValue=0
    stop_trigger = struct.pack(">HHBI", 182, 9, 0, 0)
    boundary = struct.pack(">HH", 178, 4 + len(start_trigger) + len(stop_trigger))
    boundary += start_trigger + stop_trigger

    # AISpec (183) : antenne 0xFFFF = toutes
    # AntennaCount=1, AntennaID=0
    antennas = struct.pack(">HH", 1, 0)
    # AISpecStopTrigger : type=0 (Null), DurationTrigger=0
    aispec_stop = struct.pack(">HHBI", 184, 9, 0, 0)
    # InventoryParameterSpec (186) : SpecID=1, Protocol=EPCGlobalClass1Gen2(1)
    inv_spec = struct.pack(">HHHB", 186, 7, 1, 1)
    aispec_body = antennas + aispec_stop + inv_spec
    aispec = struct.pack(">HH", 183, 4 + len(aispec_body)) + aispec_body

    # ROReportSpec (237) : trigger=Upon_N_Tags_Or_End_Of_ROSpec(1), N=1
    # + TagReportContentSelector (238) : tout à 0 (juste EPC)
    tag_report = struct.pack(">HHH", 238, 6, 0)  # vide → renvoie EPC seulement
    ror_body = struct.pack(">BH", 1, 1) + tag_report
    ror = struct.pack(">HH", 237, 4 + len(ror_body)) + ror_body

    body_inner = struct.pack(">IBB", rospec_id, priority, current_state)
    body_inner += boundary + aispec + ror
    rospec_param = struct.pack(">HH", 177, 4 + len(body_inner)) + body_inner

    return llrp_header(ADD_ROSPEC, msg_id, 10 + len(rospec_param)) + rospec_param


def build_simple_msg(msg_type: int, msg_id: int, rospec_id: int = 1) -> bytes:
    """ENABLE/START/STOP/DELETE ROSPEC — corps = juste l'ID 4 octets."""
    body = struct.pack(">I", rospec_id)
    return llrp_header(msg_type, msg_id, 10 + len(body)) + body


def parse_tag_data(body: bytes):
    """Parse un RO_ACCESS_REPORT et extrait les EPCs (param 13 ou 241)."""
    epcs = []
    i = 0
    while i < len(body):
        if i + 4 > len(body):
            break
        # Premier bit = TV (1) ou TLV (0)
        first = body[i]
        if first & 0x80:
            # TV parameter — type sur 7 bits
            ptype = first & 0x7F
            if ptype == 13:  # EPC-96 — 12 octets de données EPC + 1 octet header
                epc = body[i+1:i+13]
                epcs.append(epc.hex().upper())
                i += 13
            else:
                # autres TV (8/9/0A/0B…) on les passe : impossible à parser sans table → break safe
                i += 1
        else:
            # TLV — type 10 bits, length 16 bits
            if i + 4 > len(body): break
            ptype, length = struct.unpack(">HH", body[i:i+4])
            ptype &= 0x3FF
            if length < 4:
                break
            if ptype == 241:  # EPCData
                # +4 (TLV header) +2 (epc_length_bits) = octets EPC
                if i + 6 > len(body): break
                bit_len = struct.unpack(">H", body[i+4:i+6])[0]
                byte_len = (bit_len + 7) // 8
                epc = body[i+6:i+6+byte_len]
                epcs.append(epc.hex().upper())
            i += length
    return epcs


def run(ip: str, duration: int = 5):
    print(f"[+] Connexion à {ip}:5084 …")
    sock = socket.socket()
    sock.settimeout(5.0)
    sock.connect((ip, 5084))

    # 1) Le lecteur DEVRAIT envoyer un READER_EVENT_NOTIFICATION spontanément.
    #    Certains firmwares restent silencieux → on attend 2s puis on provoque.
    sock.settimeout(2.0)
    try:
        mt, mid, body = recv_message(sock, timeout=2.0)
        if mt == READER_EVENT_NOTIFICATION:
            print("[✓] READER_EVENT_NOTIFICATION reçu — lecteur prêt.")
        elif mt is not None:
            print(f"[?] Message reçu type={mt} ({len(body)} octets) — on continue.")
        else:
            print("[!] Aucun message après connexion — on provoque GET_READER_CAPABILITIES…")
    except socket.timeout:
        print("[!] Pas de notification spontanée — on envoie GET_READER_CAPABILITIES…")
        # Body : RequestedData=1 (All)
        cap_body = struct.pack(">B", 0)  # 0 = All capabilities
        sock.sendall(llrp_header(GET_READER_CAPABILITIES, 1, 10 + len(cap_body)) + cap_body)
        try:
            mt, mid, body = recv_message(sock, timeout=5.0)
            if mt == GET_READER_CAPABILITIES_RESPONSE:
                print(f"[✓] GET_READER_CAPABILITIES_RESPONSE reçue ({len(body)} octets) — LLRP confirmé.")
            elif mt is not None:
                print(f"[?] Réponse atypique : type={mt} ({len(body)} octets) — dump 64 premiers octets :")
                print("    " + body[:64].hex())
            else:
                print("[✗] Aucune réponse au GET_READER_CAPABILITIES — le service sur 5084 ne parle pas LLRP standard.")
                print("    Possibles causes :")
                print("      • protocole propriétaire (Impinj ItemSense / Zebra Direct / autre)")
                print("      • lecteur en mode client (c'est lui qui doit se connecter à un serveur)")
                print("      • firmware très ancien")
                sock.close(); return
        except socket.timeout:
            print("[✗] Timeout sur GET_READER_CAPABILITIES — service muet sur 5084.")
            print("    → vérifier dans l'admin du lecteur : protocole = LLRP (pas custom),")
            print("       et mode = serveur (pas client).")
            sock.close(); return

    # 2) Reset config + DELETE ROSPEC précédent (idempotence)
    sock.sendall(build_set_reader_config_reset(2))
    recv_message(sock)
    sock.sendall(build_simple_msg(DELETE_ROSPEC, 3, rospec_id=0))  # 0 = tous
    recv_message(sock)

    # 3) ADD_ROSPEC
    print("[+] Envoi ADD_ROSPEC …")
    sock.sendall(build_add_rospec(4))
    mt, _, body = recv_message(sock)
    print(f"[✓] ADD_ROSPEC_RESPONSE reçu (type={mt})")

    # 4) ENABLE_ROSPEC
    sock.sendall(build_simple_msg(ENABLE_ROSPEC, 5))
    recv_message(sock)
    # 5) START_ROSPEC
    sock.sendall(build_simple_msg(START_ROSPEC, 6))
    recv_message(sock)
    print(f"[+] Inventaire lancé pour {duration} s …")

    # 6) Boucle de lecture des RO_ACCESS_REPORT
    seen = {}
    deadline = time.time() + duration
    sock.settimeout(1.0)
    while time.time() < deadline:
        try:
            mt, mid, body = recv_message(sock, timeout=1.0)
        except socket.timeout:
            continue
        if mt is None:
            break
        if mt == RO_ACCESS_REPORT:
            # Le corps contient une suite de TagReportData (param 240)
            # On parse directement les EPCs (TV 13) à l'intérieur.
            for epc in parse_tag_data(body):
                seen[epc] = seen.get(epc, 0) + 1
                print(f"  ⇒ EPC {epc}")
        elif mt == KEEPALIVE:
            sock.sendall(llrp_header(KEEPALIVE_ACK, mid, 10))

    # 7) STOP + cleanup
    try:
        sock.sendall(build_simple_msg(STOP_ROSPEC, 99))
        recv_message(sock, timeout=2.0)
        sock.sendall(build_simple_msg(DISABLE_ROSPEC, 100))
        recv_message(sock, timeout=2.0)
        sock.sendall(build_simple_msg(DELETE_ROSPEC, 101))
        recv_message(sock, timeout=2.0)
    except Exception:
        pass
    sock.close()

    print()
    print(f"[✓] Inventaire terminé — {len(seen)} EPC unique(s) :")
    for epc, count in sorted(seen.items(), key=lambda x: -x[1]):
        print(f"    {epc}  (×{count})")
    return seen


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ip = sys.argv[1]
    dur = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    run(ip, dur)
