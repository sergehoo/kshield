# KAYDAN SHIELD

Solution de Contrôle d'Accès Intelligent pour KAYDAN GROUPE — Bureaux · Chantiers · Stockage.

## Stack

- Django 4.2 + DRF + Channels (WebSocket) + Celery (broker Redis)
- PostgreSQL + PostGIS (geofencing) — fallback SQLite en dev sans GDAL
- JWT pour les utilisateurs · HMAC SHA-256 pour les terminaux IoT
- 16 apps Django pour un découpage métier strict

## Démarrage

### En local (sans Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # adapter les valeurs
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

`DJANGO_SETTINGS_MODULE=kshield.settings.dev` est utilisé par défaut.
Si `DATABASE_URL` n'est pas renseigné et que `POSTGRES_HOST` non plus, on tombe
automatiquement sur SQLite (dev rapide sans Postgres).

### En Docker Compose

```bash
docker compose up --build
```

Démarre web (Django+Daphne), db (PostgreSQL+PostGIS), redis, minio. Ouvrir
<http://localhost:8000>.

## Données de démo

```bash
# Set complet (50 employés, 100 ouvriers, badges + 1000 scans sur 7 jours)
python manage.py seed_demo_data \
  --employees 50 --workers 100 --visitors 20 --sites 4 \
  --issue-badges --scans 1000 --days 7
```

L'option `--issue-badges` émet automatiquement les badges (NFC employés / UHF
ouvriers + casque pairé). `--scans N` génère N AccessEvent + BadgeScanEvent
réalistes répartis sur la dernière semaine, avec un mix granted/denied.

## Architecture sécurité

### Authentification API publique
Tous les endpoints DRF sont protégés par défaut (`IsAuthenticated`).
Login JWT sur `POST /api/v1/auth/login/`, refresh sur `POST /api/v1/auth/token/refresh/`.

### Authentification IoT (passerelles, lecteurs fixes)
Les terminaux signent leurs requêtes vers `/api/v1/access/scan/` avec
`HMAC-SHA256(key=secret_hash, msg="{ts}\n{METHOD}\n{path}\n{sha256(body)}")`.
Headers requis :

- `X-KShield-Key-Id` : `APIKey.public_id`
- `X-KShield-Timestamp` : epoch en secondes (tolérance ±60s, configurable)
- `X-KShield-Signature` : signature hex

Les clés sont gérées via le back-office `/api-keys/` — le secret n'est affiché
qu'une seule fois à la création (le serveur conserve uniquement le hash).

### Anti-fraude
Pipeline async via Celery. À chaque AccessEvent :
1. `access_control.tasks.dispatch_access_event` est planifié sur `transaction.on_commit`
2. `antifraud.services.evaluate()` exécute les règles actives :
   - `BADGE_LOAN` — badge utilisé par 2 holders distincts
   - `BADGE_TWICE_IN` — entrées consécutives sans sortie
   - `OUT_OF_HOURS` — scan hors plage autorisée
   - `GHOST_HELMET` — casque sans badge associé
   - `OUTSIDE_GEOFENCE` — scan hors polygone du site (Shapely)
3. `notifications.services` notifie les staff actifs en cas d'alerte
4. WebSocket broadcast vers le flux temps réel

### BLE Stillness
Les casques émettent des `BLEPresencePing`. Une tâche Celery périodique
(`attendance.tasks.ble_rollup_and_evaluate`) agrège en `BLEPresenceWindow` de
5 min puis lève un `BLEStillnessSignal` si le casque est immobile sur la durée
configurée par `KAYDAN_SHIELD["BLE_STILLNESS_THRESHOLD_MIN"]` (30 min par défaut).

À planifier dans django-celery-beat :
- `attendance.ble_rollup_and_evaluate` toutes les 5 minutes

## Tests

```bash
pytest -q                       # suite complète (96 tests)
pytest tests/test_hmac_auth.py  # ciblé HMAC
pytest -m integration           # marker dispo
```

Couverture (96 tests passing) :
- HMAC + dispatch async
- Auth + JWT + rôles
- Pointage (Punch, AttendanceDay, LeaveRequest, OvertimeRule)
- Anti-fraude (5 handlers)
- Geofence (point-in-polygon, OUTSIDE_GEOFENCE)
- BLE stillness (rollup, évaluation, idempotence)
- Visiteurs, access control, badges (lifecycle complet), administration smoke

## Documentation API

OpenAPI 3 générée par drf-spectacular. Endpoints :
- `/api/schema/` — schema OpenAPI brut
- `/api/docs/` — Swagger UI
- `/api/redoc/` — ReDoc

Tags métier dans le swagger : Acces, Badges, Employes, Equipements, Ouvriers, Visiteurs.

## Layout du projet

```
kshield/
  settings/{base,dev,prod}.py    # split par environnement
  urls.py                        # routes top-level
  asgi.py / wsgi.py / celery.py
core/                            # tenant + companies + feature flags + gateways
accounts/                        # users, rôles, permissions, JWT, HMAC
sites/                           # sites/zones/checkpoints + geofence service
employees/ ouvriers/ visitors/   # 3 segments porteurs
devices/                         # Device, Badge, Helmet, Pairing, OTA
access_control/                  # AccessEvent, AccessRule, ScanView, dispatch
attendance/                      # Punch, AttendanceDay, BLE stillness, congés
antifraud/                       # FraudRule + handlers + FraudAlert
notifications/                   # NotificationTemplate + dispatcher
audit/ reports/ mobile_sync/ ai_assistant/
administration/                  # Back-office (CRUD générique + vues custom)
templates/                       # base.html + administration/*.html
tests/                           # pytest-django, 96 tests
```

## Variables d'environnement importantes

| Variable | Usage | Dev par défaut |
|----------|-------|----------------|
| `SECRET_KEY` | Django | `django-insecure-dev-key-…` |
| `DEBUG` | Django | `True` (dev), `False` (prod) |
| `DATABASE_URL` | dj-database-url | non-set → SQLite |
| `REDIS_URL` | broker Celery + Channels | `redis://127.0.0.1:6379/0` |
| `CORS_ALLOWED_ORIGINS` | CORS | `localhost:3000,localhost:8000` |
| `CELERY_TASK_ALWAYS_EAGER` | Celery synchrone | `True` en dev |

Setting interne `KAYDAN_SHIELD` (dict, dans `settings/base.py`) :
- `BLE_STILLNESS_THRESHOLD_MIN: 30`
- `PUNCH_LATE_TOLERANCE_MIN: 10`
- `API_KEY_CLOCK_SKEW_SEC: 60`
- `VISITOR_ID_RETENTION_DAYS: 365`

## Production

`DJANGO_SETTINGS_MODULE=kshield.settings.prod` exige :
- `SECRET_KEY` (sans default)
- `ALLOWED_HOSTS` (csv)
- `DATABASE_URL` (`postgis://...` ou `postgresql://...` — auto-converti en postgis)
- `REDIS_URL`, `CORS_ALLOWED_ORIGINS`
- GDAL installé sur l'hôte (`apt-get install gdal-bin libgdal-dev` ou `brew install gdal`)

## Licence

Propriétaire — KAYDAN GROUPE © 2026.
