#!/usr/bin/env python3
"""Simule EXACTEMENT le snapshot diff de la session d'enrôlement Shield.

Utilise pyzk en synchrone. À lancer dans un terminal pendant que tu crées
manuellement des users sur le K14 (Menu → User → Add → présenter carte).

Usage :
    python3 scripts/zk_watch_users.py 10.20.1.66 120
                                       ^IP        ^durée_secondes
"""
import sys
import time
from zk import ZK


def main(ip: str, duration: int = 120):
    print(f"[+] Connexion à {ip}:4370 …")
    zk = ZK(ip, port=4370, timeout=5, password=0)
    conn = zk.connect()
    print("[✓] Connecté.")

    # Snapshot initial
    initial = conn.get_users()
    prev = {}
    for u in initial:
        prev[str(u.user_id)] = {
            "name": u.name,
            "card": int(getattr(u, "card", 0) or 0),
        }
    print(f"[+] Snapshot initial : {len(prev)} user(s)")
    for uid, info in prev.items():
        print(f"      user_id={uid:>4}  name={info['name']!r:<24}  card={info['card']}")

    print()
    print(f"[+] Surveillance pendant {duration}s… (Ctrl+C pour arrêter)")
    print(f"    → va sur le K14, fais Menu → User → Add → présente une carte")
    print()

    deadline = time.time() + duration
    poll_interval = 2

    try:
        while time.time() < deadline:
            time.sleep(poll_interval)
            try:
                current = conn.get_users()
            except Exception as exc:
                print(f"[!] get_users échec : {exc} — reconnect")
                try:
                    conn.disconnect()
                    conn = zk.connect()
                except Exception as exc2:
                    print(f"[✗] Reconnect impossible : {exc2}")
                    break
                continue

            for u in current:
                uid = str(u.user_id)
                card = int(getattr(u, "card", 0) or 0)
                if uid not in prev:
                    print(f"  ⇒ NEW USER  : user_id={uid:>4}  name={u.name!r:<24}  card={card}")
                    prev[uid] = {"name": u.name, "card": card}
                elif card and card != prev[uid].get("card", 0):
                    print(f"  ⇒ CARD CHANGE: user_id={uid:>4}  card={prev[uid].get('card',0)} → {card}")
                    prev[uid]["card"] = card

            print(".", end="", flush=True)
    except KeyboardInterrupt:
        print()
        print("[!] Arrêt manuel.")
    finally:
        conn.disconnect()
        print()
        print(f"[✓] Fin. {len(prev)} user(s) au total.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 120)
