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

        self.stdout.write(self.style.SUCCESS(
            f"\nFait : {opts['employees']} empl + {opts['workers']} ouvr + "
            f"{opts['visitors']} visit + {opts['sites']} sites"
        ))
        self.stdout.write("\nProchaines étapes :")
        self.stdout.write("  • Émettre les badges depuis /badges/")
        self.stdout.write("  • Pour générer un historique de scans, ajouter une commande seed_scans")
