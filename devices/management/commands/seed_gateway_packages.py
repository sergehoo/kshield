"""Publie les packages Kaydan Edge Gateway par plateforme (catalogue initial).

Usage :
    python manage.py seed_gateway_packages                    # crée les 7 plateformes
    python manage.py seed_gateway_packages --reset            # supprime tout d'abord
    python manage.py seed_gateway_packages --pkg-version 1.0.0

Après le seed, l'admin doit uploader les vrais binaires via /django-admin/devices/edgegatewaypackage/
(champ ``file`` pour Windows/Linux/Pi, ``docker_image`` pour Docker).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone


CATALOG = [
    {
        "platform": "windows",
        "name_template": "kshield-edge-{version}-windows-x64.msi",
        "min_os_version": "Windows 10 20H2 / Server 2019",
        "docker_image": "",
    },
    {
        "platform": "linux_deb",
        "name_template": "kshield-edge_{version}_amd64.deb",
        "min_os_version": "Ubuntu 20.04 / Debian 11",
        "docker_image": "",
    },
    {
        "platform": "linux_rpm",
        "name_template": "kshield-edge-{version}.x86_64.rpm",
        "min_os_version": "Fedora 36 / RHEL 8",
        "docker_image": "",
    },
    {
        "platform": "linux_sh",
        "name_template": "install-edge-{version}.sh",
        "min_os_version": "Linux amd64 (script universel)",
        "docker_image": "",
    },
    {
        "platform": "docker",
        "name_template": "kaydangroupe/kshield-edge:{version}",
        "min_os_version": "Docker 24+",
        "docker_image_template": "kaydangroupe/kshield-edge:{version}",
    },
    {
        "platform": "raspberry_pi",
        "name_template": "kshield-edge-{version}-arm64.deb",
        "min_os_version": "Raspberry Pi OS bookworm (arm64)",
        "docker_image": "",
    },
    {
        "platform": "mini_pc",
        "name_template": "kshield-edge-{version}-mini-pc.sh",
        "min_os_version": "Debian/Alpine industriel (BeagleBone, Rock Pi…)",
        "docker_image": "",
    },
]

DOCKER_COMPOSE_SNIPPET = """\
services:
  kshield-edge:
    image: {image}
    restart: unless-stopped
    network_mode: host
    environment:
      KSHIELD_SERVER_URL: ${{KSHIELD_SERVER_URL}}
      KSHIELD_ACTIVATION_TOKEN: ${{KSHIELD_ACTIVATION_TOKEN}}
    volumes:
      - ./kshield-edge-data:/data
"""


class Command(BaseCommand):
    help = "Publie le catalogue Kaydan Edge Gateway par plateforme."

    def add_arguments(self, parser):
        # NB : "--version" est réservé par Django (option globale de manage.py)
        # → on utilise --pkg-version à la place.
        parser.add_argument("--pkg-version", "-p", default="1.0.0",
                             dest="pkg_version",
                             help="Version du package à publier (défaut 1.0.0)")
        parser.add_argument("--reset", action="store_true",
                             help="Supprime tous les packages avant de re-seed")
        parser.add_argument("--release-notes",
                             default="Version initiale de Kaydan Edge Gateway. "
                                     "Support ZKTeco/AiFace, ONVIF, Hikvision, "
                                     "HID, Dahua, Axis, Suprema. Offline-first "
                                     "avec queue SQLite locale.")

    def handle(self, *args, **opts):
        from devices.models import EdgeGatewayPackage

        version = opts["pkg_version"]

        if opts["reset"]:
            n = EdgeGatewayPackage.objects.all().count()
            EdgeGatewayPackage.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Supprimé {n} packages"))

        # Retire le flag is_latest sur les anciennes versions de chaque plateforme
        EdgeGatewayPackage.objects.filter(is_latest=True).update(is_latest=False)

        created, updated = 0, 0
        for item in CATALOG:
            name = item["name_template"].format(version=version)
            docker_image = ""
            docker_compose = ""
            if item["platform"] == "docker":
                docker_image = item["docker_image_template"].format(version=version)
                docker_compose = DOCKER_COMPOSE_SNIPPET.format(image=docker_image)

            obj, was_created = EdgeGatewayPackage.objects.update_or_create(
                platform=item["platform"], version=version,
                defaults={
                    "name": name,
                    "docker_image": docker_image,
                    "docker_compose_snippet": docker_compose,
                    "min_os_version": item["min_os_version"],
                    "release_notes": opts["release_notes"],
                    "published_at": timezone.now(),
                    "is_latest": True,
                    "size_bytes": 0,           # à mettre à jour à l'upload du binaire
                    "checksum_sha256": "",     # idem
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f"  ✓ CREATED {obj.platform:<14} {name}")
            else:
                updated += 1
                self.stdout.write(f"  · UPDATED {obj.platform:<14} {name}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Catalogue publié : {created} créés · {updated} mis à jour · "
            f"version {version}",
        ))
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE(
            "Prochaine étape : uploader les vrais binaires via\n"
            "  /django-admin/devices/edgegatewaypackage/\n"
            "→ éditer chaque package → champ 'File' → sauvegarder\n"
            "Le SHA256 et la taille sont calculés automatiquement à l'upload.",
        ))
