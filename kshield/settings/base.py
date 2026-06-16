"""
KAYDAN SHIELD — Settings de base (commun à tous les environnements).

Ne jamais importer directement : utilisez `dev.py` ou `prod.py`.
"""
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Avec ce package settings/, le fichier est à kshield/settings/base.py
# donc BASE_DIR doit remonter de 3 niveaux pour pointer sur la racine projet.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Clé Fernet pour le chiffrement de champs sensibles (core.fields.EncryptedCharField).
# Vide → fallback dérivé de SECRET_KEY via SHA-256 (dev OK, prod : générer une vraie clé).
FIELD_ENCRYPTION_KEY = config("FIELD_ENCRYPTION_KEY", default="")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # django.contrib.gis activé conditionnellement dans dev.py/prod.py
    # quand DATABASES["default"]["ENGINE"] == postgis (nécessite GDAL natif).
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "channels",
    "django_celery_beat",
    "django_celery_results",
    "django_prometheus",   # exporter /metrics + métriques DB/cache auto
    # SSO Keycloak — chargé conditionnellement plus bas si SSO_ENABLED
]

LOCAL_APPS = [
    "core.apps.CoreConfig",
    "accounts",
    "sites",
    "employees",
    "ouvriers",
    "visitors",
    "devices",
    "access_control",
    "attendance",
    "antifraud",
    "notifications",
    "audit",
    "reports",
    "mobile_sync",
    "ai_assistant",
    "administration",
    "sso.apps.SSOConfig",  # Keycloak SSO — toujours installé pour les modèles
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",  # début monitor
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise : sert les fichiers /static/ (CSS/JS admin + Django REST Framework
    # + custom) directement depuis le conteneur, sans nginx. Doit être placé juste
    # APRÈS SecurityMiddleware pour bénéficier des en-têtes de cache.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",  # CSP + Permissions-Policy + COOP/CORP
    "core.middleware.TenantContextMiddleware",
    "audit.middleware.AuditContextMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",   # fin monitor
]

# ---------------------------------------------------------------------------
# Cookies : SameSite + HttpOnly explicites (en prod, Secure est forcé)
# ---------------------------------------------------------------------------
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # False car les requêtes JS récupèrent le token via cookie
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

ROOT_URLCONF = "kshield.urls"
WSGI_APPLICATION = "kshield.wsgi.application"
ASGI_APPLICATION = "kshield.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database (override dans dev.py / prod.py)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

# URL de redirection si non authentifié (utilisée par BaseAdminView et @login_required)
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# DRF + JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "KAYDAN SHIELD API",
    "DESCRIPTION": "Solution de Contrôle d'Accès Intelligent — Bureaux • Chantiers • Stockage",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:8000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Channels (WebSocket) — override en dev pour utiliser InMemory
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [config("REDIS_URL", default="redis://127.0.0.1:6379/0")]},
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="django-db")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TIMEZONE = config("TIME_ZONE", default="Africa/Abidjan")
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)

# ─── Celery Beat — défaut, surchargeable via DatabaseScheduler ─────────
# DatabaseScheduler ignore ce dict (utilise django_celery_beat.models). Il sert
# de fallback si on bascule sur PersistentScheduler / docs / dev local.
from celery.schedules import crontab as _crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Refresh des gauges Prometheus toutes les 30s
    "refresh_prometheus_gauges": {
        "task": "core.refresh_prometheus_gauges",
        "schedule": 30.0,
    },
    # Digest exécutif hebdomadaire — chaque lundi 07h00 Africa/Abidjan
    "weekly_executive_digest": {
        "task": "reports.generate_weekly_digest",
        "schedule": _crontab(hour=7, minute=0, day_of_week="monday"),
    },
    # Digest exécutif mensuel — chaque 1er du mois 07h30
    "monthly_executive_digest": {
        "task": "reports.generate_monthly_digest",
        "schedule": _crontab(hour=7, minute=30, day_of_month="1"),
    },
    # Sync ZKTeco — pull pointages toutes les 60s + push users toutes les 5 min
    "zkteco_sync_attendances": {
        "task": "devices.sync_zkteco_attendances",
        "schedule": 60.0,
    },
    "zkteco_push_users": {
        "task": "devices.push_zkteco_users",
        "schedule": 300.0,
    },
}

# ---------------------------------------------------------------------------
# Storage (MinIO / S3 compatible) — activé en prod via STORAGES override
# ---------------------------------------------------------------------------
# NB : Django 4.2+ remplace DEFAULT_FILE_STORAGE / STATICFILES_STORAGE par
# le dict STORAGES (déclaré plus bas dans la section static). Les vars AWS_*
# restent valides pour configurer le backend s3boto3.
AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default=None)
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default=None)
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default=None)
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="kaydan-shield")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")

# ---------------------------------------------------------------------------
# I18N / TZ
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fr"
TIME_ZONE = config("TIME_ZONE", default="Africa/Abidjan")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / Media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise : compression + cache busting (fingerprint dans le nom de fichier
# pour permettre des max-age=1 an sans risque de stale).
STORAGES = {
    "default": {
        "BACKEND": config(
            "DEFAULT_FILE_STORAGE",
            default="django.core.files.storage.FileSystemStorage",
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
# Si un fichier référencé dans CSS/JS est manquant, on ne casse PAS le build
# (manifest tolérant aux fichiers absents : utile pour admin qui réfère à des
# images optionnelles).
WHITENOISE_MANIFEST_STRICT = False
# Cache long pour les assets hashed
WHITENOISE_MAX_AGE = config("WHITENOISE_MAX_AGE", default=60 * 60 * 24 * 365, cast=int)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging (base — surchargé selon environnement)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} — {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}

# ---------------------------------------------------------------------------
# Kaydan Shield specific
# ---------------------------------------------------------------------------
KAYDAN_SHIELD = {
    "BLE_STILLNESS_THRESHOLD_MIN": 30,
    "PUNCH_LATE_TOLERANCE_MIN": 10,
    "API_KEY_CLOCK_SKEW_SEC": 60,
    "VISITOR_ID_RETENTION_DAYS": 365,
    "AUDIT_HASH_ALGO": "sha256",
    "AI_PROVIDER": config("AI_PROVIDER", default="openai"),
    "AI_MODEL": config("AI_MODEL", default="gpt-4o-mini"),
    "OPENAI_API_KEY": config("OPENAI_API_KEY", default=""),
    "SSO_OFFLINE_CACHE_TTL_HOURS": config(
        "SSO_OFFLINE_CACHE_TTL_HOURS", default=24, cast=int),
    "SMS": {
        "backend": config("SMS_BACKEND", default="console"),
        "from": config("SMS_FROM", default="KAYDAN"),
    },
    "WEBHOOKS": [],  # populé via .env JSON ou config code

    # ─── Reconnaissance faciale → confirmation présence ───────────
    # Le pipeline face NE CRÉE PAS de Punch RFID. Il enrichit avec une
    # FaceCheckinConfirmation (max 2 par employé/jour : arrival + departure).
    "FACE_PRESENCE": {
        # Heure cut-off (locale) : avant = arrival, après = departure.
        "ARRIVAL_DEPARTURE_CUTOFF_HOUR": config(
            "FACE_PRESENCE_CUTOFF_HOUR", default=14, cast=int),
        # Fenêtre face↔badge (heures) pour matcher un sighting à un Punch.
        "MATCH_WINDOW_HOURS": config(
            "FACE_PRESENCE_MATCH_WINDOW_H", default=4, cast=int),
        # Ouvre une FraudAlert FACE_NO_BADGE si visage sans badge correspondant.
        "ALERT_ON_FACE_WITHOUT_BADGE": config(
            "FACE_PRESENCE_ALERT_FACE_ONLY", default=True, cast=bool),
        "ALERT_SEVERITY": config("FACE_PRESENCE_ALERT_SEVERITY", default="medium"),
    },
    # ─── Reconnaissance faciale (InsightFace + SilentFace) ───
    # Pipeline complet : RetinaFace (détection) → ArcFace (embedding 512D)
    # → MiniFASNet (anti-spoofing). Défauts CPU-friendly ; bascule GPU via
    # FACE_CTX_ID=0 + FACE_PROVIDERS="CUDAExecutionProvider,...".
    "FACE": {
        # Master switch — si False, l'engine renvoie une erreur explicite et
        # la page admin retombe sur face-api.js client-only.
        "ENABLED": config("FACE_ENGINE_ENABLED", default=True, cast=bool),
        # Modèle InsightFace :
        #   buffalo_l = IResNet100, 512D, precision (~280 Mo, ~220 ms CPU / ~25 ms GPU)
        #   buffalo_s = MobileFaceNet, 512D, rapide   (~16 Mo,  ~95 ms CPU / ~10 ms GPU)
        # En CPU on conseille buffalo_s pour les checkpoints temps-réel.
        "MODEL_NAME": config("FACE_MODEL_NAME", default="buffalo_s"),
        # ctx_id : 0 = première GPU CUDA, -1 = CPU. Défaut CPU (universel).
        # Le moteur fallback CPU automatiquement si CUDA absent.
        "CTX_ID": config("FACE_CTX_ID", default=-1, cast=int),
        # Providers ONNX dans l'ordre. CPU par défaut, override pour GPU :
        #   FACE_PROVIDERS="CUDAExecutionProvider,CPUExecutionProvider"
        "PROVIDERS": config(
            "FACE_PROVIDERS",
            default="CPUExecutionProvider",
            cast=lambda v: [p.strip() for p in v.split(",") if p.strip()],
        ),
        # Taille d'entrée du détecteur RetinaFace (px). 640 = équilibré ;
        # baisser à 320 pour gagner 2× en CPU au prix de la détection à distance.
        "DET_SIZE": config("FACE_DET_SIZE", default=640, cast=int),
        # Score minimum de détection (0–1). En dessous, on rejette la capture.
        "MIN_DET_SCORE": config("FACE_MIN_DET_SCORE", default=0.55, cast=float),
        # Seuil par défaut de similarité cosinus pour valider un match (0–1).
        # 0.40 = tolérant. 0.60 = sécurité (recommandé KAYDAN). Plancher dur 0.50.
        "MATCH_THRESHOLD": config("FACE_MATCH_THRESHOLD", default=0.60, cast=float),
        # Cache des poids ONNX InsightFace : par défaut ~/.insightface/models/.
        "MODEL_ROOT": config("FACE_MODEL_ROOT", default=""),

        # ─── Anti-spoofing (SilentFace / MiniFASNet) ───
        # Désactivable pendant l'init si les poids sont absents (logué en warn).
        # On bloque l'enrôlement si un spoof est détecté, mais le match retourne
        # juste un score : c'est à l'app cliente de décider quoi faire.
        "LIVENESS": {
            "ENABLED": config("FACE_LIVENESS_ENABLED", default=True, cast=bool),
            # Répertoire contenant les .onnx (cf. download_face_models).
            # Défaut : <BASE_DIR>/models/silentface/
            "MODEL_DIR": config(
                "FACE_LIVENESS_MODEL_DIR",
                default=str(BASE_DIR / "models" / "silentface"),
            ),
            # Ensemble SilentFace : 2 modèles à scales différentes, on moyenne
            # les softmax puis on prend l'argmax pour la classe finale.
            # Chaque entrée : (filename, scale d'expansion bbox)
            "MODELS": [
                ("2.7_80x80_MiniFASNetV2.onnx", 2.7),
                ("4_0_0_80x80_MiniFASNetV1SE.onnx", 4.0),
            ],
            # Index de la classe "real" dans la sortie softmax (3 classes :
            # 0=fake_2D, 1=real, 2=fake_3D — convention Silent-Face-Anti-Spoofing).
            "REAL_CLASS_INDEX": config("FACE_LIVENESS_REAL_INDEX", default=1, cast=int),
            # Seuil de score real (0–1) pour valider la vivacité.
            # 0.85 = strict (rejette ~5 % de vrais visages mal cadrés).
            # 0.70 = équilibré recommandé KAYDAN.
            "THRESHOLD": config("FACE_LIVENESS_THRESHOLD", default=0.70, cast=float),
            # Bloque l'enrôlement si spoof détecté. Le match retourne juste le score.
            "BLOCK_ENROLL_ON_SPOOF": config(
                "FACE_LIVENESS_BLOCK_ENROLL", default=True, cast=bool,
            ),
        },
    },
}

# ---------------------------------------------------------------------------
# SSO Keycloak (OpenID Connect) — feature flag SSO_ENABLED
# ---------------------------------------------------------------------------
SSO_ENABLED = config("SSO_ENABLED", default=False, cast=bool)
SSO_AUTO_CREATE_USER = config("SSO_AUTO_CREATE_USER", default=True, cast=bool)
SSO_SYNC_ROLES = config("SSO_SYNC_ROLES", default=True, cast=bool)
SSO_DEFAULT_GROUP = config("SSO_DEFAULT_GROUP", default="kaydan-users")

KEYCLOAK_BASE_URL = config("KEYCLOAK_BASE_URL", default="")
KEYCLOAK_REALM = config("KEYCLOAK_REALM", default="kaydan")

# Endpoints OIDC — si non fournis, déduit depuis KEYCLOAK_BASE_URL/REALM
_kc_realm_url = (f"{KEYCLOAK_BASE_URL.rstrip('/')}/realms/{KEYCLOAK_REALM}"
                  if KEYCLOAK_BASE_URL else "")
OIDC_OP_ISSUER = config("OIDC_OP_ISSUER", default=_kc_realm_url)
OIDC_OP_AUTHORIZATION_ENDPOINT = config(
    "OIDC_OP_AUTHORIZATION_ENDPOINT",
    default=f"{_kc_realm_url}/protocol/openid-connect/auth" if _kc_realm_url else "")
OIDC_OP_TOKEN_ENDPOINT = config(
    "OIDC_OP_TOKEN_ENDPOINT",
    default=f"{_kc_realm_url}/protocol/openid-connect/token" if _kc_realm_url else "")
OIDC_OP_USER_ENDPOINT = config(
    "OIDC_OP_USER_ENDPOINT",
    default=f"{_kc_realm_url}/protocol/openid-connect/userinfo" if _kc_realm_url else "")
OIDC_OP_JWKS_ENDPOINT = config(
    "OIDC_OP_JWKS_ENDPOINT",
    default=f"{_kc_realm_url}/protocol/openid-connect/certs" if _kc_realm_url else "")
OIDC_OP_LOGOUT_ENDPOINT = config(
    "OIDC_OP_LOGOUT_ENDPOINT",
    default=f"{_kc_realm_url}/protocol/openid-connect/logout" if _kc_realm_url else "")

OIDC_RP_CLIENT_ID = config("OIDC_RP_CLIENT_ID", default="kaydan-shield-web")
OIDC_RP_CLIENT_SECRET = config("OIDC_RP_CLIENT_SECRET", default="")
OIDC_RP_SCOPES = config("OIDC_RP_SCOPES", default="openid profile email")
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_VERIFY_SSL = config("OIDC_VERIFY_SSL", default=True, cast=bool)

# Branchage mozilla-django-oidc
OIDC_CALLBACK_CLASS = "sso.views.SSOCallbackView"
OIDC_AUTHENTICATE_CLASS = "sso.views.SSOLoginView"
OIDC_AUTHENTICATION_CALLBACK_URL = "sso:callback"
OIDC_USERNAME_ALGO = "sso.utils.extract_user_claims"  # ignoré, fallback default
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"

# Authentication backends — ajoute le backend OIDC quand SSO_ENABLED
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # fallback local toujours dispo
]
if SSO_ENABLED:
    AUTHENTICATION_BACKENDS.insert(0, "sso.backends.KaydanOIDCBackend")
    THIRD_PARTY_APPS.append("mozilla_django_oidc")
    INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
