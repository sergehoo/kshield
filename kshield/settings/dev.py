"""
KAYDAN SHIELD — Settings de développement.

Activer avec : `export DJANGO_SETTINGS_MODULE=kshield.settings.dev`
"""
from decouple import Csv, config

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, INSTALLED_APPS, MIDDLEWARE, REST_FRAMEWORK

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
DEBUG = True
ALLOWED_HOSTS = ["*"]

SECRET_KEY = config(
    "SECRET_KEY",
    default="django-insecure-dev-key-do-not-use-in-prod-9w2x6py-yt(uzz",
)

# ---------------------------------------------------------------------------
# Database — Postgres + PostGIS (recommandé). SQLite fallback.
#
# Priorité de configuration :
#   1. DATABASE_URL (postgres://… ou postgis://…)
#   2. POSTGRES_HOST / POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD
#      → utilise django.contrib.gis.db.backends.postgis
#   3. SQLite local (fallback dev sans Postgres)
# ---------------------------------------------------------------------------
def _build_databases():
    url = config("DATABASE_URL", default="")
    # Priorité 1 : DATABASE_URL explicite
    if url:
        try:
            import dj_database_url
            cfg = dj_database_url.parse(url)
            # Force PostGIS dès que c'est du postgres + on a la lib gis
            if cfg.get("ENGINE", "").endswith("postgresql"):
                cfg["ENGINE"] = "django.contrib.gis.db.backends.postgis"
            return {"default": cfg}
        except ImportError:
            # dj_database_url absent → on parse manuellement
            pass

    # Priorité 2 : variables granulaires Postgres
    pg_host = config("POSTGRES_HOST", default="")
    if pg_host:
        return {
            "default": {
                "ENGINE": "django.contrib.gis.db.backends.postgis",
                "NAME": config("POSTGRES_DB", default="kaydan_shield"),
                "USER": config("POSTGRES_USER", default="kaydan_user"),
                "PASSWORD": config("POSTGRES_PASSWORD", default=""),
                "HOST": pg_host,
                "PORT": config("POSTGRES_PORT", default="5432"),
                "OPTIONS": {
                    "sslmode": config("POSTGRES_SSLMODE", default="prefer"),
                },
            },
        }

    # Priorité 3 : SQLite local (utile pour démo rapide / tests sans Postgres)
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        },
    }


DATABASES = _build_databases()

# ---------------------------------------------------------------------------
# GIS — activer django.contrib.gis SEULEMENT si la base est PostGIS
# (évite l'erreur "Could not find the GDAL library" quand on tourne en SQLite)
# ---------------------------------------------------------------------------
if DATABASES["default"]["ENGINE"].endswith("postgis"):
    INSTALLED_APPS = [*INSTALLED_APPS, "django.contrib.gis"]

# ---------------------------------------------------------------------------
# Email — console en dev
# ---------------------------------------------------------------------------
# EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Channels — InMemory pour ne pas dépendre de Redis en dev local
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

# ---------------------------------------------------------------------------
# Celery — exécution synchrone par défaut en dev
# ---------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=True, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# ---------------------------------------------------------------------------
# CORS — large en dev
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# DRF — autoriser navigateur API et ouvrir certains throttles
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
    "DEFAULT_THROTTLE_RATES": {"anon": "1000/min", "user": "10000/min"},
}

# ---------------------------------------------------------------------------
# Toolbar (optionnel, ne plante pas si non installé)
# ---------------------------------------------------------------------------
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]
    INTERNAL_IPS = ["127.0.0.1"]

    # ProfilingPanel : désactivé (incompatible Python 3.14 — cProfile.runcall
    # rejette deux profilers simultanés).
    # RedirectsPanel : désactivé (déprécié + intercepte les 302 sur upload/save
    # ce qui interrompt la navigation normale après un POST).
    DEBUG_TOOLBAR_PANELS = [
        "debug_toolbar.panels.history.HistoryPanel",
        "debug_toolbar.panels.versions.VersionsPanel",
        "debug_toolbar.panels.timer.TimerPanel",
        "debug_toolbar.panels.settings.SettingsPanel",
        "debug_toolbar.panels.headers.HeadersPanel",
        "debug_toolbar.panels.request.RequestPanel",
        "debug_toolbar.panels.sql.SQLPanel",
        "debug_toolbar.panels.staticfiles.StaticFilesPanel",
        "debug_toolbar.panels.templates.TemplatesPanel",
        "debug_toolbar.panels.alerts.AlertsPanel",
        "debug_toolbar.panels.cache.CachePanel",
        "debug_toolbar.panels.signals.SignalsPanel",
        # "debug_toolbar.panels.redirects.RedirectsPanel",  # ← désactivé (intercepte 302)
        # "debug_toolbar.panels.profiling.ProfilingPanel",  # ← désactivé (Python 3.14)
        "debug_toolbar.panels.logging.LoggingPanel",
    ]
    # Belt-and-braces : même si le panel est listé, ce flag force Django à ne pas
    # intercepter les redirections.
    DEBUG_TOOLBAR_CONFIG = {
        "INTERCEPT_REDIRECTS": False,
    }
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging — DEBUG bavard
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "DEBUG"},
    "loggers": {
        "django.db.backends": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "django.request": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        "kshield": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
    },
}
