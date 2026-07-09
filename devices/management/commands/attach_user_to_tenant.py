"""Rattache un user à un tenant (utile quand un compte a été créé sans lien).

Usage :
    python manage.py attach_user_to_tenant --email serge.ogah@kaydangroupe.com
    python manage.py attach_user_to_tenant --email … --tenant "Kaydan"
    python manage.py attach_user_to_tenant --all-missing     # attache tous les
                                                              # users sans tenant
                                                              # au premier tenant actif
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Attache un ou plusieurs users à un tenant."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Email du user à rattacher.")
        parser.add_argument("--tenant",
                             help="Nom du tenant cible (défaut : premier actif).")
        parser.add_argument("--all-missing", action="store_true",
                             help="Attache tous les users sans tenant.")
        parser.add_argument("--create-default", action="store_true",
                             help="Crée un tenant 'Kaydan' si aucun n'existe.")

    def handle(self, *args, **opts):
        from accounts.models import User
        from core.models import Tenant

        # Résolution du tenant
        tenant = None
        if opts["tenant"]:
            tenant = Tenant.objects.filter(name=opts["tenant"]).first()
            if tenant is None:
                self.stderr.write(self.style.ERROR(
                    f"Tenant '{opts['tenant']}' introuvable."))
                return
        else:
            tenant = Tenant.objects.filter(is_active=True).first()

        if tenant is None and opts["create_default"]:
            tenant = Tenant.objects.create(name="Kaydan", slug="kaydan",
                                             is_active=True)
            self.stdout.write(self.style.SUCCESS(
                f"Tenant 'Kaydan' créé (id={tenant.id})"))

        if tenant is None:
            self.stderr.write(self.style.ERROR(
                "Aucun tenant en base. Utilise --create-default."))
            return

        self.stdout.write(f"Tenant cible : {tenant.name} (id={tenant.id})")

        # Sélection users
        if opts["all_missing"]:
            users = User.objects.filter(tenant__isnull=True)
        elif opts["email"]:
            users = User.objects.filter(email=opts["email"])
        else:
            self.stderr.write(self.style.ERROR(
                "Passer --email <adresse> ou --all-missing."))
            return

        count = 0
        for u in users:
            u.tenant = tenant
            u.save(update_fields=["tenant"])
            self.stdout.write(f"  ✓ {u.email or u.username} → tenant #{tenant.id}")
            count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n{count} user(s) rattaché(s) au tenant '{tenant.name}'."))
