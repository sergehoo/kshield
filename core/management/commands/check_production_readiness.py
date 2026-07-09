"""KAYDAN SHIELD — Vérification pre-flight avant mise en production.

Usage :
    python manage.py check_production_readiness

Le script effectue une trentaine de checks (sécurité, DB, cache, storage,
Channels, Celery, migrations, statics, secrets…). Il retourne un code de
sortie 0 si tout est OK, 1 si des warnings, 2 si des erreurs bloquantes.

Ne modifie RIEN — pur diagnostic.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand


class Check:
    def __init__(self, name: str):
        self.name = name
        self.status = "ok"      # ok | warn | fail | skip
        self.detail = ""

    def ok(self, detail=""):    self.status = "ok"; self.detail = detail
    def warn(self, detail):     self.status = "warn"; self.detail = detail
    def fail(self, detail):     self.status = "fail"; self.detail = detail
    def skip(self, detail):     self.status = "skip"; self.detail = detail


class Command(BaseCommand):
    help = "Vérifie l'état de production readiness de Kaydan Shield."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true",
                             help="Warnings deviennent bloquants.")

    def handle(self, *args, **opts):
        checks: list[Check] = []
        self._check_debug(checks)
        self._check_secret_key(checks)
        self._check_allowed_hosts(checks)
        self._check_field_encryption(checks)
        self._check_https(checks)
        self._check_database(checks)
        self._check_redis(checks)
        self._check_channels(checks)
        self._check_celery(checks)
        self._check_storage(checks)
        self._check_email(checks)
        self._check_cors(checks)
        self._check_migrations(checks)
        self._check_static(checks)
        self._check_daphne(checks)
        self._check_sentry(checks)
        self._check_mqtt(checks)
        self._check_axes(checks)
        self._check_drivers(checks)
        self._check_beat(checks)
        self._check_admin_user(checks)

        # Reporting
        oks = [c for c in checks if c.status == "ok"]
        warns = [c for c in checks if c.status == "warn"]
        fails = [c for c in checks if c.status == "fail"]
        skips = [c for c in checks if c.status == "skip"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("KAYDAN SHIELD — Production Readiness"))
        self.stdout.write("=" * 60)
        for c in checks:
            icon = {"ok": "✓", "warn": "⚠", "fail": "✗", "skip": "…"}[c.status]
            style = {"ok": self.style.SUCCESS, "warn": self.style.WARNING,
                      "fail": self.style.ERROR, "skip": self.style.NOTICE}[c.status]
            line = f"  {icon} {c.name:<40} {c.detail}"
            self.stdout.write(style(line))
        self.stdout.write("=" * 60)
        self.stdout.write(
            f"{len(oks)} OK · {len(warns)} warnings · "
            f"{len(fails)} errors · {len(skips)} skipped",
        )

        if fails:
            self.stderr.write(self.style.ERROR(
                "\n✗ NOT READY — des erreurs bloquantes doivent être corrigées.",
            ))
            sys.exit(2)
        if warns and opts["strict"]:
            self.stderr.write(self.style.WARNING(
                "\n⚠ Strict mode — des warnings sont présents.",
            ))
            sys.exit(1)
        if warns:
            self.stdout.write(self.style.WARNING(
                "\n⚠ READY WITH WARNINGS — à corriger avant prod, pas bloquant.",
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n✓ PRODUCTION READY.",
            ))

    # ─── Checks ──────────────────────────────────────────────────
    def _check_debug(self, checks):
        c = Check("DEBUG désactivé")
        if settings.DEBUG:
            c.fail("DEBUG=True — DOIT être False en prod")
        else:
            c.ok("DEBUG=False")
        checks.append(c)

    def _check_secret_key(self, checks):
        c = Check("SECRET_KEY sécurisée")
        sk = settings.SECRET_KEY or ""
        if not sk or "insecure" in sk or "change-me" in sk:
            c.fail("SECRET_KEY est un placeholder")
        elif len(sk) < 40:
            c.warn(f"SECRET_KEY courte ({len(sk)} chars, recommandé ≥50)")
        else:
            c.ok(f"{len(sk)} chars")
        checks.append(c)

    def _check_allowed_hosts(self, checks):
        c = Check("ALLOWED_HOSTS configuré")
        hosts = settings.ALLOWED_HOSTS
        if not hosts or hosts == ["localhost", "127.0.0.1"]:
            c.fail("ALLOWED_HOSTS ne contient que localhost")
        elif "*" in hosts:
            c.warn("ALLOWED_HOSTS='*' — restreindre au domaine prod")
        else:
            c.ok(", ".join(hosts))
        checks.append(c)

    def _check_field_encryption(self, checks):
        c = Check("FIELD_ENCRYPTION_KEY définie")
        key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
        if not key:
            c.warn("Non définie → fallback dérivé du SECRET_KEY (moins sûr)")
        elif len(key) < 40:
            c.warn(f"Trop courte ({len(key)} chars)")
        else:
            c.ok("Fernet key OK")
        checks.append(c)

    def _check_https(self, checks):
        c = Check("HTTPS strict")
        conditions = [
            getattr(settings, "SECURE_SSL_REDIRECT", False),
            getattr(settings, "SESSION_COOKIE_SECURE", False),
            getattr(settings, "CSRF_COOKIE_SECURE", False),
            getattr(settings, "SECURE_HSTS_SECONDS", 0) > 0,
        ]
        if all(conditions):
            c.ok(f"HSTS {settings.SECURE_HSTS_SECONDS}s + secure cookies")
        elif settings.DEBUG:
            c.skip("DEBUG=True")
        else:
            c.fail(f"HTTPS non complet : SSL_REDIRECT={conditions[0]}, "
                     f"COOKIE_SECURE={conditions[1]}, HSTS={conditions[3]}")
        checks.append(c)

    def _check_database(self, checks):
        c = Check("Database PostgreSQL")
        engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
        if "postgresql" in engine or "postgis" in engine:
            c.ok(engine.rsplit(".", 1)[-1])
        elif "sqlite" in engine:
            c.fail("SQLite détecté — obligatoirement PG en prod")
        else:
            c.warn(f"Engine inconnue : {engine}")
        checks.append(c)

    def _check_redis(self, checks):
        c = Check("Redis joignable")
        try:
            from django.core.cache import cache
            cache.set("__prod_check__", "ok", 5)
            v = cache.get("__prod_check__")
            if v == "ok":
                c.ok("cache set/get OK")
            else:
                c.fail("cache lecture KO")
        except Exception as exc:
            c.fail(f"Cache KO : {exc}")
        checks.append(c)

    def _check_channels(self, checks):
        c = Check("Channels + channel layer")
        try:
            from channels.layers import get_channel_layer
            layer = get_channel_layer()
            if layer is None:
                c.warn("Aucun channel layer configuré")
            else:
                cls = layer.__class__.__name__
                if "InMemory" in cls:
                    c.warn("InMemoryChannelLayer — OK dev, PAS pour prod")
                else:
                    c.ok(cls)
        except Exception as exc:
            c.fail(str(exc))
        checks.append(c)

    def _check_celery(self, checks):
        c = Check("Celery broker")
        try:
            eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
            if eager:
                c.fail("CELERY_TASK_ALWAYS_EAGER=True — pas de vraie async prod")
            else:
                broker = getattr(settings, "CELERY_BROKER_URL", "")
                if not broker:
                    c.fail("CELERY_BROKER_URL non défini")
                else:
                    c.ok(urlparse(broker).scheme)
        except Exception as exc:
            c.fail(str(exc))
        checks.append(c)

    def _check_storage(self, checks):
        c = Check("Stockage fichiers")
        storages = getattr(settings, "STORAGES", {})
        default = storages.get("default", {}).get("BACKEND", "")
        if "S3Boto3" in default or "MinIO" in default:
            c.ok("S3/MinIO")
        elif settings.DEBUG:
            c.skip("FileSystemStorage (DEBUG=True)")
        else:
            c.warn(f"Stockage local : {default} — prévoir S3/MinIO")
        checks.append(c)

    def _check_email(self, checks):
        c = Check("SMTP configuré")
        host = getattr(settings, "EMAIL_HOST", "")
        user = getattr(settings, "EMAIL_HOST_USER", "")
        if not host:
            c.warn("EMAIL_HOST vide — emails non fonctionnels")
        elif not user and not settings.DEBUG:
            c.warn(f"{host} sans EMAIL_HOST_USER")
        else:
            c.ok(host)
        checks.append(c)

    def _check_cors(self, checks):
        c = Check("CORS strict")
        if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
            c.fail("CORS_ALLOW_ALL_ORIGINS=True — restreindre")
        else:
            origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
            if origins:
                c.ok(f"{len(origins)} origins")
            elif settings.DEBUG:
                c.skip("dev")
            else:
                c.warn("CORS_ALLOWED_ORIGINS vide — front bloqué")
        checks.append(c)

    def _check_migrations(self, checks):
        c = Check("Migrations appliquées")
        try:
            from django.db.migrations.executor import MigrationExecutor
            from django.db import connection
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                c.fail(f"{len(plan)} migration(s) non appliquée(s) — run migrate")
            else:
                c.ok("toutes appliquées")
        except Exception as exc:
            c.warn(str(exc))
        checks.append(c)

    def _check_static(self, checks):
        c = Check("Static files collectés")
        static_root = getattr(settings, "STATIC_ROOT", "")
        if not static_root:
            c.warn("STATIC_ROOT non défini")
        elif not os.path.isdir(static_root):
            if settings.DEBUG:
                c.skip("STATIC_ROOT non collecté (DEBUG)")
            else:
                c.fail(f"{static_root} manquant — lancer collectstatic")
        else:
            n = sum(len(files) for _, _, files in os.walk(static_root))
            c.ok(f"{n} fichiers dans {static_root}")
        checks.append(c)

    def _check_daphne(self, checks):
        c = Check("daphne en tête d'INSTALLED_APPS (Channels 4)")
        if settings.INSTALLED_APPS[0] == "daphne":
            c.ok("daphne en 1ère position")
        else:
            c.fail(f"1er app = {settings.INSTALLED_APPS[0]} — WebSocket non supporté")
        checks.append(c)

    def _check_sentry(self, checks):
        c = Check("Sentry monitoring")
        dsn = os.environ.get("SENTRY_DSN", "").strip()
        if dsn:
            if dsn.startswith(("http://", "https://")) and "@" in dsn:
                c.ok("DSN configuré")
            else:
                c.warn("SENTRY_DSN malformé — désactivé")
        else:
            c.warn("SENTRY_DSN non défini — pas d'error tracking")
        checks.append(c)

    def _check_mqtt(self, checks):
        c = Check("MQTT/EMQX")
        host = os.environ.get("MQTT_HOST", "")
        if not host:
            c.warn("MQTT_HOST non défini — désactivé")
        elif os.environ.get("MQTT_TLS", "False").lower() in ("true", "1") \
             or os.environ.get("MQTT_PORT") == "8883":
            c.ok(f"{host} (TLS)")
        elif settings.DEBUG:
            c.skip("dev clair")
        else:
            c.warn(f"{host} sans TLS — activer MQTT_TLS=True en prod")
        checks.append(c)

    def _check_axes(self, checks):
        c = Check("Rate limit login (django-axes)")
        try:
            import axes  # noqa
            c.ok(f"axes {axes.__version__ if hasattr(axes, '__version__') else 'installé'}")
        except ImportError:
            c.warn("django-axes non installé")
        checks.append(c)

    def _check_drivers(self, checks):
        c = Check("Driver Framework chargé")
        try:
            from devices.drivers import DriverManager
            drivers = DriverManager.list_drivers()
            c.ok(f"{len(drivers)} vendors")
        except Exception as exc:
            c.warn(str(exc))
        checks.append(c)

    def _check_beat(self, checks):
        c = Check("Celery beat tasks")
        schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
        if not schedule:
            c.warn("Aucune task périodique définie")
        else:
            c.ok(f"{len(schedule)} tasks planifiées")
        checks.append(c)

    def _check_admin_user(self, checks):
        c = Check("Superuser existe")
        try:
            from accounts.models import User
            n = User.objects.filter(is_superuser=True, is_active=True).count()
            if n == 0:
                c.fail("Aucun superuser actif — createsuperuser requis")
            else:
                c.ok(f"{n} superuser(s)")
        except Exception as exc:
            c.warn(str(exc))
        checks.append(c)
