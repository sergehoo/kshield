"""KAYDAN SHIELD — Génère des données de démo réalistes (employés, ouvriers,
visiteurs, sites, badges, scans).

Usage :
    python manage.py seed_demo_data --employees 100 --workers 200 --visitors 50 --days 30
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Génère des données de démo pour KAYDAN SHIELD."

    def add_arguments(self, parser):
        parser.add_argument("--employees", type=int, default=50)
        parser.add_argument("--workers", type=int, default=100)
        parser.add_argument("--visitors", type=int, default=20)
        parser.add_argument("--sites", type=int, default=4)
        parser.add_argument("--days", type=int, default=14,
                             help="Nombre de jours d'historique de scans")
        parser.add_argument("--scans", type=int, default=0,
                             help="Nombre d'AccessEvent à générer répartis sur --days "
                                  "(0 = aucun, 1000 recommandé pour démo).")
        parser.add_argument("--issue-badges", action="store_true",
                             help="Émet des badges pour 80%% des employés et ouvriers.")
        parser.add_argument("--reset", action="store_true",
                             help="Vide les tables avant de seeder.")

    def handle(self, *args, **opts):
        try:
            from faker import Faker
        except ImportError:
            self.stderr.write("Faker non installé : pip install faker")
            return

        fake = Faker("fr_FR")
        Faker.seed(42)
        random.seed(42)

        from core.models import Company
        from core.services import KaydanTenantService
        from employees.models import Department, Employee, JobPosition
        from ouvriers.models import Subcontractor, Trade, Worker
        from visitors.models import Visitor
        from sites.models import Site
        from devices.models import Helmet
        from devices.services import BadgeWorkflowService

        if opts["reset"]:
            self.stdout.write("Vidage des tables…")
            from devices.models import Badge, BadgeAssignment, BadgeScanEvent
            from access_control.models import AccessEvent
            BadgeScanEvent.objects.all().delete()
            BadgeAssignment.objects.all().delete()
            Badge.objects.all().delete()
            AccessEvent.objects.all().delete()
            Helmet.objects.all().delete()
            Employee.objects.all().delete()
            Worker.objects.all().delete()
            Visitor.objects.all().delete()

        # Tenant
        tenant = KaydanTenantService.get()
        self.stdout.write(f"✓ Tenant {tenant.name}")

        # Filiales
        FILIALES = [
            ("kaydan-btp", "KAYDAN BTP", "btp"),
            ("kaydan-log", "KAYDAN Logistique", "logistics"),
            ("kaydan-ind", "KAYDAN Industrie", "industry"),
            ("kaydan-trd", "KAYDAN Trading", "trading"),
        ]
        companies = []
        for code, name, sector in FILIALES:
            c, _ = Company.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={"name": name, "sector": sector, "is_active": True},
            )
            companies.append(c)
        self.stdout.write(f"✓ {len(companies)} filiales")

        # Sites
        SITE_TYPES = [("office","Bureau"),("construction","Chantier"),
                      ("warehouse","Entrepôt"),("mixed","Mixte")]
        sites = []
        for i in range(opts["sites"]):
            stype, slabel = SITE_TYPES[i % len(SITE_TYPES)]
            s, _ = Site.objects.get_or_create(
                tenant=tenant, code=f"site-{i+1:02d}",
                defaults={
                    "name": f"{slabel} {fake.city()}",
                    "type": stype, "company": random.choice(companies),
                    "status": "active", "timezone": "Africa/Abidjan",
                    "latitude": 5.32 + random.random() * 0.05,
                    "longitude": -4.05 + random.random() * 0.05,
                },
            )
            sites.append(s)
        self.stdout.write(f"✓ {len(sites)} sites")

        # Trades + sous-traitants
        TRADES = ["macon","ferrailleur","conducteur-engin","electricien","plombier","peintre"]
        trades = []
        for code in TRADES:
            t, _ = Trade.objects.get_or_create(code=code,
                defaults={"name": code.replace("-"," ").title()})
            trades.append(t)

        SUBS = ["ETS Bâtir+", "ETS Construct CI", "ETS Tropical Build"]
        subs = []
        for i, name in enumerate(SUBS):
            s, _ = Subcontractor.objects.get_or_create(
                tenant=tenant, code=f"sub-{i+1}",
                defaults={"name": name, "is_active": True},
            )
            subs.append(s)

        # Departments + positions
        for c in companies[:1]:  # juste sur la 1ère pour ne pas exploser
            for d_code in ["finance","rh","tech","commercial"]:
                Department.objects.get_or_create(
                    company=c, code=d_code,
                    defaults={"name": d_code.upper()},
                )
            for p_code in ["chef-projet","comptable","ingenieur","commercial"]:
                JobPosition.objects.get_or_create(
                    company=c, code=p_code,
                    defaults={"title": p_code.replace("-"," ").title()},
                )

        # Employés
        self.stdout.write(f"Génération de {opts['employees']} employés…")
        for i in range(opts["employees"]):
            comp = random.choice(companies)
            wl = random.choice(["office", "field", "both"])
            Employee.objects.get_or_create(
                tenant=tenant, matricule=f"EMP-{i+1:04d}",
                defaults={
                    "company": comp,
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                    "email": fake.email(),
                    "phone": f"+225 0{random.randint(1,9)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}",
                    "contract_type": random.choice(["cdi","cdi","cdd","internship"]),
                    "status": "active",
                    "work_location": wl,
                    "hired_at": fake.date_between(start_date="-3y", end_date="-1m"),
                },
            )

        # Ouvriers
        self.stdout.write(f"Génération de {opts['workers']} ouvriers…")
        for i in range(opts["workers"]):
            Worker.objects.get_or_create(
                tenant=tenant, matricule=f"OV-{i+1:04d}",
                defaults={
                    "first_name": fake.first_name_male(),
                    "last_name": fake.last_name(),
                    "trade": random.choice(trades),
                    "subcontractor": random.choice(subs) if random.random() < 0.7 else None,
                    "phone": f"+225 0{random.randint(1,9)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}",
                    "status": "active",
                },
            )

        # Visiteurs
        self.stdout.write(f"Génération de {opts['visitors']} visiteurs…")
        for i in range(opts["visitors"]):
            Visitor.objects.get_or_create(
                tenant=tenant, id_number=f"CNI-{1000000+i}",
                defaults={
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                    "email": fake.email(),
                    "phone": f"+225 0{random.randint(1,9)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)} {random.randint(10,99)}",
                    "id_type": "cni",
                    "company": fake.company(),
                },
            )

        # ---------------------------------------------------------------
        # Émission de badges (option --issue-badges)
        # ---------------------------------------------------------------
        if opts.get("issue_badges"):
            self.stdout.write("Émission des badges (80% des employés + ouvriers)…")
            from devices.services import BadgeWorkflowService
            issued = 0

            for emp in Employee.objects.filter(tenant=tenant)[: int(opts["employees"] * 0.8)]:
                try:
                    if not emp.badge:  # n'a pas déjà un badge actif
                        BadgeWorkflowService.issue_employee_badge(emp)
                        issued += 1
                except Exception:
                    pass

            # ouvriers : besoin d'un casque, on en crée à la volée
            for w in Worker.objects.filter(tenant=tenant)[: int(opts["workers"] * 0.8)]:
                try:
                    if w.badge:
                        continue
                    helmet, _ = Helmet.objects.get_or_create(
                        tenant=tenant, serial_number=f"HLM-{w.matricule}",
                        defaults={
                            "uhf_tag_uid": f"UHF-{w.matricule}",
                            "ble_beacon_uid": f"BLE-{w.matricule}",
                            "status": "active",
                        },
                    )
                    BadgeWorkflowService.issue_worker_badge(w, helmet=helmet)
                    issued += 1
                except Exception:
                    pass
            self.stdout.write(f"✓ {issued} badges émis")

        # ---------------------------------------------------------------
        # Génération de scans / AccessEvent (option --scans N)
        # ---------------------------------------------------------------
        scan_count = int(opts.get("scans") or 0)
        if scan_count > 0:
            self.stdout.write(f"Génération de {scan_count} scans répartis sur "
                               f"{opts['days']} jours…")
            self._seed_scans(tenant, sites, scan_count, days=opts["days"])

        self.stdout.write(self.style.SUCCESS(
            f"\nFait : {opts['employees']} empl + {opts['workers']} ouvr + "
            f"{opts['visitors']} visit + {opts['sites']} sites"
            + (f" + {scan_count} scans" if scan_count else "")
        ))
        self.stdout.write("\nProchaines étapes :")
        if not opts.get("issue_badges"):
            self.stdout.write("  • Émettre les badges : --issue-badges")
        if not scan_count:
            self.stdout.write("  • Générer un historique de scans : --scans 1000")

    # =================================================================
    # Helpers
    # =================================================================
    def _seed_scans(self, tenant, sites, count, days=14):
        """Génère AccessEvent + BadgeScanEvent réalistes."""
        from datetime import timedelta

        from django.contrib.contenttypes.models import ContentType

        from access_control.models import AccessDecision, AccessEvent
        from devices.models import Badge, BadgeScanEvent, Device, DeviceModel
        from employees.models import Employee
        from ouvriers.models import Worker
        from visitors.models import Visitor

        if not sites:
            self.stdout.write("  Aucun site → impossible de générer des scans.")
            return

        # Assure-toi qu'on a au moins un Device par site
        dm, _ = DeviceModel.objects.get_or_create(
            brand="Demo", model="NFC-Reader-Demo",
            defaults={"type": "nfc_reader", "is_active": True},
        )
        for s in sites:
            Device.objects.get_or_create(
                tenant=tenant, model=dm,
                serial_number=f"DEV-{s.code}",
                defaults={"site": s, "status": "active"},
            )

        # Pool de badges actifs avec leurs holders
        badges = list(Badge.objects.filter(
            tenant=tenant, status__in=("active", "assigned"),
        ).select_related("paired_helmet")[:500])

        if not badges:
            self.stdout.write("  Aucun badge actif → utilise --issue-badges d'abord.")
            return

        now = timezone.now()
        decisions_distribution = (
            ["granted"] * 80 + ["denied"] * 15 + ["review"] * 5
        )
        denial_reasons = ["BADGE_INCONNU", "BADGE_EXPIRED", "OUT_OF_HOURS",
                          "ZONE_RESTRICTED", "CASQUE_MANQUANT"]

        events = []
        for i in range(count):
            badge = random.choice(badges)
            site = random.choice(sites)
            device = Device.objects.filter(site=site).first()
            offset_min = random.randint(0, days * 24 * 60)
            ts = now - timedelta(minutes=offset_min)
            decision = random.choice(decisions_distribution)
            reason = random.choice(denial_reasons) if decision == "denied" else ""

            holder_kind = badge.holder_kind or "employee"
            ev = AccessEvent.objects.create(
                tenant=tenant, site=site, device=device,
                timestamp=ts, badge_uid=badge.uid,
                helmet_uid=badge.paired_helmet.uhf_tag_uid if badge.paired_helmet else "",
                holder_kind=holder_kind,
                holder_object_id=badge.holder_object_id,
                direction=random.choice(["in", "in", "in", "out"]),
                method=random.choice(["nfc", "uhf", "qr"]),
                decision=decision, denial_reason=reason,
            )
            AccessDecision.objects.create(event=ev, deciding_rule_code=reason or "OK")
            BadgeScanEvent.objects.create(
                badge=badge, site=site,
                timestamp=ts, decision=decision,
                method=ev.method, access_event=ev,
            )
            events.append(ev)
            if (i + 1) % 100 == 0:
                self.stdout.write(f"  {i+1}/{count}…")

        self.stdout.write(f"✓ {len(events)} scans générés "
                           f"(badges actifs={len(badges)}, sites={len(sites)})")
