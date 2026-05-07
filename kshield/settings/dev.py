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
# Database — SQLite local par défaut, Postgres si DATABASE_URL fourni
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
_DB_URL = config("DATABASE_URL", default="")
if _DB_URL.startswith("postgres"):
    try:
        import dj_database_url

        DATABASES["default"] = dj_database_url.parse(_DB_URL)
    except ImportError:
        pass

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
