"""Seed des DeviceModel standards KAYDAN SHIELD.

Crée (ou met à jour) les modèles d'équipements officiellement supportés :
- MOKO H7 Lite          (beacon BLE casque ouvrier)
- FOCUS ST-G8           (portique RFID UHF gate antenna)
- ZKTeco K14/ID         (terminal pointage carte + clavier)
- ZKTeco K20            (variante avec empreinte)
- HikVision DS-2CD      (caméra IP générique)

Idempotent : ré-exécutable. Update si déjà présent.

Usage :
    python manage.py seed_device_models
    python manage.py seed_device_models --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from devices.models import DeviceModel


_SEED = [
    # ─── BLE beacons casques ouvriers ───
    {
        "brand": "MOKO",
        "model": "H7 Lite",
        "type": "beacon_ble",
        "spec": {
            "category": "helmet_ble_beacon",
            "protocol": "iBeacon + Eddystone",
            "frequency_ghz": 2.4,
            "tx_power_dbm": -4,        # configurable de -40 à +4 dBm
            "advertising_interval_ms": 1000,
            "battery": "CR2032",
            "battery_life_months": 24,
            "ingress_protection": "IP67",
            "mac_address_format": "AA:BB:CC:DD:EE:FF",
            "uuid_default": "FDA50693-A4E2-4FB1-AFCF-C6EB07647825",
            "weight_g": 7,
            "use_case": "Fixé sur casque ouvrier — broadcast continu, capté par "
                          "gateways BLE site ou app mobile contrôleur.",
        },
        "is_active": True,
    },

    # ─── UHF gate antenna ───
    {
        "brand": "FOCUS",
        "model": "ST-G8",
        "type": "portique",
        "spec": {
            "category": "uhf_gate_antenna",
            "protocol": "LLRP",
            "llrp_port": 5084,
            "frequency_band": "ETSI 865-868 MHz / FCC 902-928 MHz",
            "tx_power_dbm_range": [20, 33],
            "antennas_count": 4,        # 4 ports antennes
            "read_range_m": 8,
            "polarization": "Circulaire",
            "anti_collision": "EPC Gen2 / ISO 18000-6C",
            "throughput_tags_per_sec": 200,
            "interfaces": ["Ethernet 10/100", "RS-232", "GPIO"],
            "use_case": "Portique d'entrée/sortie chantier — détecte les tags "
                          "UHF (badges + casques) sans contact, jusqu'à 8 m.",
            "checkpoint_recommended_type": "entry",   # ou "exit"/"bidirectional"
        },
        "is_active": True,
    },

    # ─── ZKTeco K14/ID (déjà créé en prod, on met à jour la spec) ───
    {
        "brand": "ZKTeco",
        "model": "K14/ID",
        "type": "reader_nfc_fixed",
        "spec": {
            "category": "access_terminal",
            "protocol": "ZKAccess SDK",
            "sdk_port": 4370,
            "rfid_freq": "125 kHz EM",
            "keypad": True,
            "fingerprint": False,
            "platform": "ZLM60_TFT",
            "screen": "TFT 2.4\"",
            "users_capacity": 1000,
            "logs_capacity": 50000,
            "interfaces": ["Ethernet", "Wiegand out"],
            "use_case": "Terminal pointage employé bureau — carte 125 kHz + PIN.",
        },
        "is_active": True,
    },

    {
        "brand": "ZKTeco",
        "model": "K20",
        "type": "reader_nfc_fixed",
        "spec": {
            "category": "access_terminal",
            "protocol": "ZKAccess SDK",
            "sdk_port": 4370,
            "rfid_freq": "125 kHz EM",
            "keypad": True,
            "fingerprint": True,
            "users_capacity": 3000,
            "logs_capacity": 100000,
            "interfaces": ["Ethernet", "USB", "Wiegand out"],
            "use_case": "Terminal pointage + empreinte digitale.",
        },
        "is_active": True,
    },

    # ─── Caméra HikVision standard ───
    {
        "brand": "HikVision",
        "model": "DS-2CD2143G0",
        "type": "camera",
        "spec": {
            "category": "camera_ip",
            "protocol": "ONVIF + RTSP",
            "rtsp_port": 554,
            "onvif_port": 80,
            "resolution": "4MP",
            "ir_distance_m": 30,
            "ip_rating": "IP67",
            "poe": True,
            "use_case": "Surveillance entrée site + face recognition.",
        },
        "is_active": True,
    },
]


class Command(BaseCommand):
    help = "Seed les DeviceModel standards (MOKO, FOCUS, ZKTeco, HikVision)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche ce qui serait créé sans toucher la DB.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        created = updated = unchanged = 0
        for s in _SEED:
            key = {"brand": s["brand"], "model": s["model"]}
            defaults = {
                "type": s["type"],
                "spec": s["spec"],
                "is_active": s["is_active"],
            }
            if dry:
                exists = DeviceModel.objects.filter(**key).exists()
                self.stdout.write(
                    f"[dry] {'UPDATE' if exists else 'CREATE'} "
                    f"{s['brand']} {s['model']} (type={s['type']})"
                )
                continue
            obj, was_created = DeviceModel.objects.get_or_create(
                **key, defaults=defaults,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Créé : {obj}"
                ))
            else:
                changed = False
                for k, v in defaults.items():
                    if getattr(obj, k) != v:
                        setattr(obj, k, v)
                        changed = True
                if changed:
                    obj.save()
                    updated += 1
                    self.stdout.write(self.style.WARNING(
                        f"↻ Mis à jour : {obj}"
                    ))
                else:
                    unchanged += 1

        if not dry:
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Seed terminé : {created} créé(s), {updated} mis à jour, "
                f"{unchanged} inchangé(s)"
            ))
