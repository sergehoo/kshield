#!/usr/bin/env python3
"""Test de communication avec un terminal ZKTeco (K14, K20, F18, MA300…).

Usage :
    python3 scripts/zk_test.py <ip> [port=4370] [password=0]

Le script :
  1. Se connecte au terminal sur le port ZKAccess SDK (4370 par défaut),
  2. Récupère firmware / serial / capacités,
  3. Liste les utilisateurs enregistrés (max 20 affichés),
  4. Liste les 10 derniers events de pointage,
  5. Affiche les empreintes / cartes RFID disponibles.
"""
import sys

try:
    from zk import ZK, const
except ImportError:
    print("Module 'pyzk' manquant. Installer :  pip install pyzk")
    sys.exit(1)


def run(ip: str, port: int = 4370, password: int = 0):
    print(f"[+] Connexion à {ip}:{port} (mot de passe={password}) …")
    zk = ZK(ip, port=port, timeout=5, password=password, force_udp=False, ommit_ping=False)

    try:
        conn = zk.connect()
    except Exception as exc:
        print(f"[✗] Connexion échouée : {exc}")
        print()
        print("    Causes possibles :")
        print("      • mot de passe terminal ≠ 0 → tester :  python3 scripts/zk_test.py %s %d 1234" % (ip, port))
        print("      • port différent → essayer 4380, 80, 8080, 8081")
        print("      • protocole forcé UDP : modifier force_udp=True dans le script")
        return

    print("[✓] Connecté !")
    print()

    # ── Infos device ─────────────────────────────────────────────────
    try:
        print("Firmware  :", conn.get_firmware_version())
    except Exception as e: print("Firmware  : (n/a)", e)
    try:
        print("Serial    :", conn.get_serialnumber())
    except Exception as e: print("Serial    : (n/a)", e)
    try:
        print("Nom       :", conn.get_device_name())
    except Exception as e: print("Nom       : (n/a)", e)
    try:
        print("Plateforme:", conn.get_platform())
    except Exception as e: print("Plateforme: (n/a)", e)
    try:
        print("Heure     :", conn.get_time())
    except Exception as e: print("Heure     : (n/a)", e)
    try:
        users_count = len(conn.get_users())
        print(f"Utilisateurs enregistrés : {users_count}")
    except Exception as e:
        users_count = 0
        print("Utilisateurs : (n/a)", e)

    print()

    # ── Utilisateurs (max 20) ────────────────────────────────────────
    try:
        print("=== Utilisateurs (premiers 20) ===")
        for u in conn.get_users()[:20]:
            card = getattr(u, "card", 0) or 0
            print(f"  ID={u.user_id:>6}  nom={u.name!r:<24}  carte={card:>10}  privilège={u.privilege}")
    except Exception as e:
        print("Erreur lecture users :", e)

    print()

    # ── Derniers events de pointage ──────────────────────────────────
    try:
        print("=== 10 derniers pointages ===")
        attendances = conn.get_attendance()[-10:]
        for a in attendances:
            print(f"  {a.timestamp}  user_id={a.user_id}  status={a.status}  punch={a.punch}")
    except Exception as e:
        print("Erreur lecture attendances :", e)

    # ── Empreintes ──────────────────────────────────────────────────
    try:
        templates = conn.get_templates()
        print()
        print(f"Empreintes enregistrées : {len(templates)}")
    except Exception as e:
        print("Empreintes : (n/a)", e)

    conn.disconnect()
    print()
    print("[✓] Déconnexion propre.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ip = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 4370
    password = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    run(ip, port, password)
