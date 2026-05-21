"""Scan ONVIF du LAN pour découvrir les caméras IP.

Usage :
    python manage.py discover_cameras                                 # juste lister
    python manage.py discover_cameras --user admin --pass xxx         # avec creds
    python manage.py discover_cameras --create --site 1 --user admin --pass xxx
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Découverte ONVIF WS-Discovery des caméras IP sur le LAN."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=5,
                            help="Durée du multicast en secondes (def 5).")
        parser.add_argument("--user", default="",
                            help="Identifiant ONVIF (admin).")
        parser.add_argument("--pass", dest="passwd", default="",
                            help="Mot de passe ONVIF.")
        parser.add_argument("--create", action="store_true",
                            help="Créer automatiquement les caméras trouvées.")
        parser.add_argument("--site", type=int, default=None,
                            help="ID Site auquel rattacher les caméras créées.")

    def handle(self, *args, **opts):
        try:
            from devices.onvif_discovery import discover_cameras, OnvifUnavailable
        except ImportError:
            self.stderr.write(self.style.ERROR("Module onvif_discovery introuvable."))
            return

        creds = None
        if opts["user"] and opts["passwd"]:
            creds = {"user": opts["user"], "pass": opts["passwd"]}

        self.stdout.write(self.style.NOTICE(
            f"-> Scan WS-Discovery (timeout={opts['timeout']}s)…"
        ))
        try:
            results = discover_cameras(
                timeout=opts["timeout"],
                fetch_streams=creds is not None,
                credentials=creds,
            )
        except OnvifUnavailable as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Discovery failed: {exc}"))
            return

        if not results:
            self.stdout.write(self.style.WARNING(
                "Aucune caméra trouvée. Vérifier :\n"
                "  - Le PC et les caméras sont sur le même VLAN.\n"
                "  - Le multicast 239.255.255.250:3702 n'est pas bloqué.\n"
                "  - ONVIF est activé sur les caméras (à vérifier dans leur WebUI)."
            ))
            return

        # Affichage
        self.stdout.write(self.style.SUCCESS(f"\n[OK] {len(results)} caméra(s) :\n"))
        for r in results:
            self.stdout.write(f"  - {r['name']} @ {r['ip']}")
            if r.get("manufacturer"):
                self.stdout.write(f"      Modèle: {r['manufacturer']} {r['model'] or ''}")
            if r.get("rtsp_url"):
                self.stdout.write(f"      RTSP : {r['rtsp_url']}")
            if r.get("xaddr"):
                self.stdout.write(f"      ONVIF: {r['xaddr']}")
            if r.get("onvif_error"):
                self.stdout.write(self.style.WARNING(f"      Err  : {r['onvif_error']}"))

        # Création auto si demandée
        if opts["create"]:
            if not opts["site"]:
                self.stderr.write(self.style.ERROR(
                    "--create nécessite --site <pk> pour rattacher les caméras."
                ))
                return
            from devices.models import Camera
            from sites.models import Site
            try:
                site = Site.objects.get(pk=opts["site"])
            except Site.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Site #{opts['site']} introuvable."))
                return

            created = 0
            for r in results:
                if not r.get("rtsp_url"):
                    self.stdout.write(self.style.WARNING(
                        f"  [skip] {r['name']} : pas d'URL RTSP (credentials manquants ?)"
                    ))
                    continue
                cam, was_created = Camera.objects.get_or_create(
                    rtsp_url=r["rtsp_url"],
                    defaults={
                        "name": r.get("name") or f"Caméra {r['ip']}",
                        "site": site,
                        "location_label": (
                            f"{r.get('manufacturer','')} "
                            f"{r.get('model','')}".strip() or r["ip"] or ""
                        ),
                        "username": opts["user"] or "",
                        "password": opts["passwd"] or "",
                        "transport": "tcp",
                        "codec": "h264",
                        "onvif_enabled": True,
                        "onvif_host": r.get("ip") or "",
                        "is_active": True,
                    },
                )
                if was_created:
                    self.stdout.write(self.style.SUCCESS(
                        f"  [+] créée: {cam.name} (#{cam.pk})"
                    ))
                    created += 1
                else:
                    self.stdout.write(f"  [=] existe déjà: {cam.name} (#{cam.pk})")
            self.stdout.write(self.style.SUCCESS(f"\nTotal créées: {created}"))
