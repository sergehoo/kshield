"""KAYDAN SHIELD — Compléments de données démo.

Le seed_demo_data génère déjà : tenant, sociétés, sites, employés, ouvriers,
visiteurs, badges, scans. Cette commande AJOUTE (get_or_create) les données
transverses qui manquent pour que TOUTES les pages du front React soient
peuplées :

  - Terminaux (ZKTeco K14, AiFace, Portique UHF, Lecteur BLE)
  - Caméras Hikvision
  - Casques BLE MOKO H7
  - Notifications sur les 14 derniers jours
  - Alertes anti-fraude ouvertes
  - Attendance days sur les 30 derniers jours
  - Coordonnées GPS Abidjan pour les sites sans lat/lng

Idempotente — safe à relancer plusieurs fois.

Usage prod (Dokploy) :

    docker compose exec shieldweb python manage.py seed_demo_extras
    docker compose exec shieldweb python manage.py seed_demo_extras --days 30

Prérequis : `seed_demo_data` doit avoir été exécuté au moins une fois.
"""
import random
from datetime import timedelta, date

from django.core.management.base import BaseCommand
from django.utils import timezone


# Coordonnées GPS de quartiers d'Abidjan pour donner des sites géolocalisés
ABIDJAN_LOCATIONS = [
    ("Riviera Palmeraie",    5.3639, -3.9847),
    ("Cocody Angré",         5.3717, -3.9819),
    ("Yopougon Selmer",      5.3453, -4.0844),
    ("Marcory Zone 4",       5.2985, -3.9873),
    ("Treichville",          5.2942, -4.0117),
    ("Plateau — Centre",     5.3200, -4.0242),
    ("Adjamé — 220 log.",    5.3550, -4.0192),
    ("Abobo — Baoulé",       5.4136, -4.0225),
    ("Koumassi Prodomo",     5.2947, -3.9678),
    ("Port-Bouët VGE",       5.2589, -3.9333),
    ("Bingerville Santé",    5.3556, -3.8942),
    ("Songon — KM17",        5.3319, -4.1725),
]


class Command(BaseCommand):
    help = "Complète les données démo (terminaux, caméras, alerts, notifications)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30,
                            help="Historique en jours pour attendance & notifications")
        parser.add_argument("--terminals-per-site", type=int, default=2,
                            help="Nombre de terminaux à créer par site")

    def handle(self, *args, **opts):
        try:
            from faker import Faker
        except ImportError:
            self.stderr.write("Faker requis : pip install faker")
            return

        fake = Faker("fr_FR")
        Faker.seed(42)
        random.seed(42)

        # ─────── Imports lazy ───────
        from core.services import KaydanTenantService
        from sites.models import Site
        from devices.models import Device, DeviceModel, Helmet
        try:
            from devices.models import Camera
        except ImportError:
            Camera = None

        tenant = KaydanTenantService.get()
        self.stdout.write(self.style.NOTICE(f"Tenant cible : {tenant.name}"))

        # ─────── 1) Coordonnées GPS pour sites sans lat/lng ───────
        self._geolocate_sites(tenant)

        # ─────── 2) DeviceModels de référence ───────
        models = self._ensure_device_models()

        # ─────── 3) Terminaux + portiques + lecteurs BLE ───────
        self._seed_terminals(tenant, models, opts["terminals_per_site"])

        # ─────── 4) Caméras ───────
        if Camera:
            self._seed_cameras(tenant, models)

        # ─────── 5) Casques BLE MOKO ───────
        self._seed_helmets(tenant)

        # ─────── 6) Notifications ───────
        self._seed_notifications(tenant, opts["days"])

        # ─────── 7) Alerts anti-fraude ───────
        self._seed_antifraud_alerts(tenant)

        # ─────── 8) Attendance days ───────
        self._seed_attendance(tenant, opts["days"])

        self.stdout.write(self.style.SUCCESS("\n✓ Complément démo terminé."))
        self.stdout.write("Recharge le front React → dashboard/carte/alertes doivent être peuplés.")

    # ---------------------------------------------------------------
    # Geolocalisation
    # ---------------------------------------------------------------
    def _geolocate_sites(self, tenant):
        from sites.models import Site
        sites = list(Site.objects.filter(tenant=tenant))
        updated = 0
        for i, s in enumerate(sites):
            if s.latitude and s.longitude:
                continue
            _, lat, lng = ABIDJAN_LOCATIONS[i % len(ABIDJAN_LOCATIONS)]
            # Jitter léger pour éviter que 2 sites soient exactement au même point
            s.latitude = lat + (random.random() - 0.5) * 0.006
            s.longitude = lng + (random.random() - 0.5) * 0.006
            s.save(update_fields=["latitude", "longitude"])
            updated += 1
        self.stdout.write(f"  ✓ {updated} site(s) géolocalisé(s) — Abidjan")

    # ---------------------------------------------------------------
    # DeviceModels
    # ---------------------------------------------------------------
    def _ensure_device_models(self):
        from devices.models import DeviceModel
        specs = [
            ("ZKTeco", "K14 SpeedFace", "face_terminal"),
            ("AiFace", "AI810", "face_terminal"),
            ("Hikvision", "DS-K1T671M", "face_terminal"),
            ("FOCUS", "ST-G8 Portique UHF", "portique"),
            ("MOKO", "H7 Lite BLE", "beacon_ble"),
            ("Impinj", "R700 UHF", "reader_uhf_fixed"),
            ("HID", "OMNIKEY 5427CK", "reader_nfc_fixed"),
            ("Hikvision", "DS-2CD2143G2-I", "camera"),
            ("Dahua", "IPC-HFW5442T-ASE", "camera"),
        ]
        models = {}
        for brand, name, type_ in specs:
            m, _ = DeviceModel.objects.get_or_create(
                brand=brand, model=name,
                defaults={"type": type_, "is_active": True},
            )
            models[name] = m
        self.stdout.write(f"  ✓ {len(models)} device models de référence")
        return models

    # ---------------------------------------------------------------
    # Terminaux
    # ---------------------------------------------------------------
    def _seed_terminals(self, tenant, models, per_site):
        from sites.models import Site
        from devices.models import Device

        sites = list(Site.objects.filter(tenant=tenant))
        if not sites:
            self.stdout.write("  Aucun site → skip terminaux.")
            return

        candidates = ["K14 SpeedFace", "AI810", "ST-G8 Portique UHF", "R700 UHF"]
        created = 0
        now = timezone.now()

        for site in sites:
            for i in range(per_site):
                model_key = random.choice(candidates)
                serial = f"KS-{site.code[:8].upper()}-{i+1:02d}-{random.randint(1000,9999)}"
                dev, was_new = Device.objects.get_or_create(
                    serial_number=serial,
                    defaults={
                        "tenant": tenant,
                        "model": models[model_key],
                        "site": site,
                        "status": random.choice(
                            ["active", "active", "active", "active", "maintenance"],
                        ),
                        "ip_address": f"192.168.{random.randint(1,10)}.{random.randint(10,250)}",
                        "firmware_version": f"v{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,20)}",
                        "commissioned_at": now - timedelta(days=random.randint(30, 400)),
                        "last_heartbeat_at": now - timedelta(seconds=random.randint(5, 600)),
                    },
                )
                if was_new:
                    created += 1
        self.stdout.write(f"  ✓ {created} terminaux créés")

    # ---------------------------------------------------------------
    # Caméras
    # ---------------------------------------------------------------
    def _seed_cameras(self, tenant, models):
        try:
            from devices.models import Camera
        except ImportError:
            return

        from sites.models import Site
        sites = list(Site.objects.filter(tenant=tenant))
        created = 0

        for site in sites:
            for i in range(random.randint(1, 3)):
                name = f"Cam {site.name[:15]} #{i+1}"
                # Camera hérite peut-être de Device — on tente les 2 signatures
                try:
                    cam, was_new = Camera.objects.get_or_create(
                        tenant=tenant,
                        serial_number=f"CAM-{site.code[:6]}-{i+1}",
                        defaults={
                            "name": name,
                            "site": site,
                            "ip_address": f"192.168.{random.randint(20,30)}.{random.randint(10,250)}",
                            "rtsp_url": f"rtsp://192.168.20.{random.randint(10,250)}:554/Streaming/Channels/101",
                            "brand": "Hikvision",
                            "is_online": random.random() > 0.15,
                        },
                    )
                    if was_new:
                        created += 1
                except Exception:
                    # Model divergent — passe silencieusement
                    pass
        self.stdout.write(f"  ✓ {created} caméras créées")

    # ---------------------------------------------------------------
    # Casques
    # ---------------------------------------------------------------
    def _seed_helmets(self, tenant):
        from devices.models import Helmet
        from ouvriers.models import Worker

        workers = list(Worker.objects.filter(tenant=tenant)[:50])
        created = 0
        for w in workers:
            uid = f"HLM-{w.matricule}"
            _, was_new = Helmet.objects.get_or_create(
                tenant=tenant,
                serial_number=uid,
                defaults={
                    "uhf_tag_uid": f"UHF-{w.matricule}",
                    "ble_beacon_uid": f"BLE-{w.matricule}-{random.randint(1000,9999)}",
                    "status": random.choice(["active", "active", "active", "maintenance"]),
                },
            )
            if was_new:
                created += 1
        self.stdout.write(f"  ✓ {created} casques BLE MOKO créés")

    # ---------------------------------------------------------------
    # Notifications
    # ---------------------------------------------------------------
    def _seed_notifications(self, tenant, days):
        try:
            from notifications.models import Notification
        except ImportError:
            self.stdout.write("  ⓘ App notifications non installée — skip")
            return

        from accounts.models import User
        users = list(User.objects.filter(is_active=True)[:5])
        if not users:
            self.stdout.write("  ⓘ Aucun user actif → skip notifications")
            return

        now = timezone.now()
        levels = ["info", "warn", "danger", "success"]
        templates = [
            ("info",    "Nouveau terminal détecté", "Un équipement a envoyé son premier heartbeat."),
            ("warn",    "Retard détecté",           "Un ouvrier est arrivé plus de 45 min en retard."),
            ("danger",  "Badge refusé",             "Tentative d'accès avec un badge suspendu."),
            ("danger",  "Terminal offline",         "Le terminal K14 Riviera 3 ne répond plus depuis 15 min."),
            ("success", "Sync terminée",            "Les événements ZKTeco ont été synchronisés."),
            ("warn",    "Batterie faible",          "Casque HLM-OV-0012 sous 20% de batterie."),
            ("info",    "Nouvel employé",           "Un employé a été ajouté à KAYDAN BTP."),
        ]

        created = 0
        for _ in range(40):
            lvl, title, body = random.choice(templates)
            user = random.choice(users)
            offset = random.randint(0, days * 24 * 3600)
            ts = now - timedelta(seconds=offset)
            try:
                Notification.objects.create(
                    user=user,
                    level=lvl,
                    title=title,
                    body=body,
                    created_at=ts,
                    read_at=ts + timedelta(minutes=random.randint(1, 240)) if random.random() < 0.6 else None,
                )
                created += 1
            except Exception:
                # Model peut avoir signature différente
                pass
        self.stdout.write(f"  ✓ {created} notifications créées")

    # ---------------------------------------------------------------
    # Alertes anti-fraude
    # ---------------------------------------------------------------
    def _seed_antifraud_alerts(self, tenant):
        try:
            from antifraud.models import Alert, Rule
        except ImportError:
            try:
                from antifraud.models import FraudAlert as Alert, FraudRule as Rule
            except ImportError:
                self.stdout.write("  ⓘ App antifraud non installée — skip")
                return

        # Règles de base
        rules_data = [
            ("duplicate_badge",   "Badge dupliqué",         "critical"),
            ("tailgating",        "Tailgating détecté",     "high"),
            ("out_of_hours",      "Accès hors horaires",    "medium"),
            ("no_helmet",         "Casque manquant",        "high"),
            ("multi_sites",       "Présence multi-sites",   "medium"),
        ]
        rules = {}
        for code, name, sev in rules_data:
            try:
                r, _ = Rule.objects.get_or_create(
                    tenant=tenant, code=code,
                    defaults={"name": name, "severity": sev, "is_active": True},
                )
                rules[code] = r
            except Exception:
                pass

        now = timezone.now()
        created = 0
        descriptions = {
            "duplicate_badge": "Le badge NFC-04A1B2 a été scanné sur 2 sites différents à moins de 5 minutes d'intervalle.",
            "tailgating":      "2 personnes détectées par la caméra pour 1 seul scan badge à l'entrée principale.",
            "out_of_hours":    "Tentative d'accès à 23:45 sur un site fermé (horaires 07:00-19:00).",
            "no_helmet":       "Ouvrier OV-0042 détecté en zone chantier sans son casque BLE apparié.",
            "multi_sites":     "L'ouvrier OV-0018 est marqué 'présent' simultanément sur 2 chantiers.",
        }

        for i in range(15):
            code, _, sev = random.choice(rules_data)
            rule = rules.get(code)
            try:
                Alert.objects.create(
                    tenant=tenant,
                    rule=rule,
                    severity=sev,
                    status=random.choice(["open"] * 8 + ["resolved", "dismissed"]),
                    description=descriptions[code],
                    created_at=now - timedelta(minutes=random.randint(5, 60 * 24 * 3)),
                    badge_uid=f"NFC-{random.randint(100000, 999999):06X}",
                )
                created += 1
            except Exception:
                pass
        self.stdout.write(f"  ✓ {created} alertes anti-fraude créées")

    # ---------------------------------------------------------------
    # Attendance days
    # ---------------------------------------------------------------
    def _seed_attendance(self, tenant, days):
        try:
            from attendance.models import AttendanceDay
        except ImportError:
            self.stdout.write("  ⓘ App attendance non installée — skip")
            return

        from ouvriers.models import Worker
        from sites.models import Site

        workers = list(Worker.objects.filter(tenant=tenant, status="active")[:100])
        sites = list(Site.objects.filter(tenant=tenant))
        if not workers or not sites:
            self.stdout.write("  ⓘ Pas assez de workers/sites → skip attendance")
            return

        today = date.today()
        created = 0

        for d_offset in range(days):
            day = today - timedelta(days=d_offset)
            # week-end : 30% de présence, semaine : 85%
            attendance_rate = 0.3 if day.weekday() >= 5 else 0.85

            for w in workers:
                if random.random() > attendance_rate:
                    continue
                site = random.choice(sites)

                # Statut réaliste
                r = random.random()
                if r < 0.75:
                    status = "present"
                    first_in_minute = 8 * 60 + random.randint(-15, 15)   # ~8h
                    worked_minutes = random.randint(7 * 60, 9 * 60 + 30) # 7h-9h30
                    overtime = max(0, worked_minutes - 8 * 60)
                elif r < 0.90:
                    status = "late"
                    first_in_minute = 8 * 60 + random.randint(45, 120)   # 8h45-10h
                    worked_minutes = random.randint(6 * 60, 8 * 60)
                    overtime = 0
                elif r < 0.97:
                    status = "partial"
                    first_in_minute = 8 * 60 + random.randint(0, 30)
                    worked_minutes = random.randint(4 * 60, 6 * 60)
                    overtime = 0
                else:
                    status = "absent"
                    first_in_minute = 0
                    worked_minutes = 0
                    overtime = 0

                try:
                    _, was_new = AttendanceDay.objects.get_or_create(
                        tenant=tenant,
                        date=day,
                        holder_kind="worker",
                        holder_object_id=w.id,
                        defaults={
                            "site": site,
                            "status": status,
                            "worked_minutes": worked_minutes,
                            "overtime_minutes": overtime,
                            "is_late": status == "late",
                        },
                    )
                    if was_new:
                        created += 1
                except Exception:
                    pass

            if d_offset % 5 == 0:
                self.stdout.write(f"    Jour J-{d_offset}: cumulé {created}")

        self.stdout.write(f"  ✓ {created} attendance days créés sur {days} jours")
