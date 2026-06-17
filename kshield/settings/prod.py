"""
KAYDAN SHIELD — Settings de production.

Activer avec : `export DJANGO_SETTINGS_MODULE=kshield.settings.prod`

Variables d'environnement obligatoires :
- SECRET_KEY
- ALLOWED_HOSTS (csv)
- DATABASE_URL (postgres://...)
- REDIS_URL
- CORS_ALLOWED_ORIGINS
"""
from decouple import Csv, config

from .base import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# Sécurité — STRICT
# ---------------------------------------------------------------------------
DEBUG = False
SECRET_KEY = config("SECRET_KEY")  # explose si manquant
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())

# HTTPS / proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# CSP : reporting endpoint optionnel
CSP_REPORT_ONLY = config("CSP_REPORT_ONLY", default=False, cast=bool)

# ---------------------------------------------------------------------------
# Database — PostGIS impératif (geofencing zones + sites)
# ---------------------------------------------------------------------------
try:
    import dj_database_url

    _db_cfg = dj_database_url.parse(
        config("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
    )
    # Force PostGIS (toutes les bases prod sont géo-localisées)
    if _db_cfg.get("ENGINE", "").endswith("postgresql"):
        _db_cfg["ENGINE"] = "django.contrib.gis.db.backends.postgis"
    DATABASES = {"default": _db_cfg}
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "dj-database-url est requis en production : pip install dj-database-url"
    ) from exc

# ---------------------------------------------------------------------------
# GIS — django.contrib.gis activé en prod (PostGIS toujours forcé ci-dessus)
# Nécessite GDAL côté image Docker : `apt-get install -y gdal-bin libgdal-dev`
# ---------------------------------------------------------------------------
if DATABASES["default"]["ENGINE"].endswith("postgis"):
    INSTALLED_APPS = [*INSTALLED_APPS, "django.contrib.gis"]  # noqa: F405

# ---------------------------------------------------------------------------
# Email — SMTP réel
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.eu.mailgun.org")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="no-reply@kaydangroupe.com")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ---------------------------------------------------------------------------
# Stockage S3 / MinIO obligatoire en prod
# ---------------------------------------------------------------------------
# Override du backend "default" (media uploadés). Le "staticfiles" reste géré
# par WhiteNoise (cf. base.py). Django 4.2+ : on utilise STORAGES dict.
STORAGES = {
    **STORAGES,    # noqa: F405 — hérité de base.py
    "default": {
        "BACKEND": config(
            "DEFAULT_FILE_STORAGE",
            default="storages.backends.s3boto3.S3Boto3Storage",
        ),
    },
}
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = True
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "path"

# ---------------------------------------------------------------------------
# Channels — Redis obligatoire
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [config("REDIS_URL")]},
    }
}

# ---------------------------------------------------------------------------
# Celery — broker Redis impératif, pas d'eager
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=config("REDIS_URL"))
CELERY_TASK_ALWAYS_EAGER = False

# ---------------------------------------------------------------------------
# CORS — strict
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", cast=Csv())

# ---------------------------------------------------------------------------
# Throttle — production
# ---------------------------------------------------------------------------
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "30/min",
    "user": "300/min",
}

# ---------------------------------------------------------------------------
# Sentry (optionnel)
# ---------------------------------------------------------------------------
import re as _re_sentry

_SENTRY_DSN = (config("SENTRY_DSN", default="") or "").strip()
# Valide qu'on a un VRAI DSN Sentry (https://<key>@<host>/<project_id>),
# pas un placeholder du genre '...' ou 'https://...@sentry.io/...'.
# Sinon Sentry crash le démarrage.
_SENTRY_DSN_VALID = bool(_re_sentry.match(
    r"^https?://[a-z0-9]{16,}@[a-z0-9.\-]+(\:\d+)?/\d+$",
    _SENTRY_DSN, _re_sentry.IGNORECASE,
))
if _SENTRY_DSN and _SENTRY_DSN_VALID:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[DjangoIntegration(), CeleryIntegration()],
            traces_sample_rate=config("SENTRY_TRACES_RATE", default=0.05, cast=float),
            send_default_pii=False,
            environment=config("SENTRY_ENVIRONMENT", default="production"),
        )
    except ImportError:
        pass
    except Exception as _exc:
        # On loggue mais on ne bloque PAS le démarrage si Sentry est down/mal configuré
        import logging as _lg
        _lg.getLogger(__name__).warning("Sentry init failed: %s", _exc)
elif _SENTRY_DSN:
    # DSN présent mais malformé → on previent dans les logs
    import logging as _lg
    _lg.getLogger(__name__).warning(
        "SENTRY_DSN défini mais malformé (%r) — Sentry désactivé. "
        "Format attendu : https://<key>@<host>/<project_id>",
        _SENTRY_DSN[:40] + "..." if len(_SENTRY_DSN) > 40 else _SENTRY_DSN,
    )

# ---------------------------------------------------------------------------
# Logging — JSON-friendly (structlog si dispo, sinon verbose)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {process:d} {thread:d} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "kshield": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
