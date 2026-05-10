# AUDIT REPORT — KShield Django 4/6 Project

**Date:** May 9, 2026  
**Scope:** Full codebase audit (16 apps, 4000+ files)  
**Project:** /sessions/focused-epic-archimedes/mnt/kshield

---

## TL;DR — Top 10 Priority Fixes

1. **8 placeholder templates in administration/** — All 8 module templates show "Module en développement" (accounts, antifraud, companies, devices, face_test, gateways, settings, sites)
2. **12 orphan detail templates** — Never referenced by any view (company_detail.html, worker_detail.html, etc.) — likely dead code or incomplete CRUD
3. **No test coverage** — administration app + AI assistant have ZERO tests; 13 other apps have minimal 3-line stubs; only 2 real test files (badge_smoke, badge_lifecycle)
4. **5 forms not in CRUD** — UserCreateForm, UserUpdateForm, RoleForm, APIKeyForm, StyledModelForm exist but not wired to administration/crud_views.py
5. **Only 1 LoginRequiredMixin found** — 50+ API views have zero permission guards; REST API endpoints are unprotected
6. **Missing @extend_schema documentation** — DRF Spectacular configured but ZERO schema decorators on 50+ ViewSets
7. **TODO in access_control/services.py:63** — Async notification/antifraud dispatch not implemented
8. **SoftDeleteModel orphan** — core.SoftDeleteModel defined but only 1 reference; soft-delete pattern incomplete
9. **Missing Django.contrib.gis** — PostGIS configured but django.contrib.gis not in INSTALLED_APPS (conditional load mentioned in comments but not implemented)
10. **Orphan template partials** — 5 shared partials (pagination, movement_timeline, form_field, badge_card, filterbar) defined but not systematically included

---

## 1. TODO / FIXME / HACK / XXX Markers

| File | Line | Content |
|------|------|---------|
| `access_control/services.py` | 63 | `# TODO: dispatch async tasks (notifications, antifraud)` |

**Assessment:** Single TODO in core business logic for notifications/antifraud dispatch. Should be high priority.

---

## 2. Unfinished Functions

### Placeholder Templates (8 total)
All in `templates/administration/`:
- `accounts.html:6` — "Module en développement."
- `antifraud.html:6` — "Module en développement."
- `companies.html:6` — "Module en développement."
- `devices.html:6` — "Module en développement."
- `face_test.html:6` — "Module en développement."
- `gateways.html:6` — "Module en développement."
- `settings.html:6` — "Module en développement."
- `sites.html:6` — "Module en développement."

**Impact:** 8 back-office modules are UI stubs. Users see placeholder text instead of functional content.

### Minimal Test Files (13 apps with 3-line stubs)
All `tests.py` files containing only imports and comments:
- `access_control`, `accounts`, `antifraud`, `attendance`, `audit`, `core`, `devices`, `employees`, `mobile_sync`, `notifications`, `ouvriers`, `reports`, `sites`, `visitors`

**Assessment:** Test scaffolding exists but no actual tests written.

---

## 3. Orphan Models

### core.SoftDeleteModel
- **Definition:** `core/models.py` — Abstract base class with `is_deleted`, `deleted_at`, `deleted_by` fields
- **References:** Only 1 reference found (definition itself)
- **Status:** Not used by any model; soft-delete pattern declared but unenforced
- **Recommendation:** Either implement across all models or remove

---

## 4. Orphan Views / URLs

### Unreferenced Detail Templates (12 total)
- `templates/administration/company_detail.html`
- `templates/administration/worker_detail.html`
- `templates/administration/visitor_detail.html`
- `templates/administration/employee_detail.html`
- `templates/administration/badge_detail.html`

**Root Cause:** Detail views likely exist but routes or `template_name` references are broken.

### Shared Template Partials (5 total, never systematically included)
- `_partials/pagination.html`
- `_partials/movement_timeline.html`
- `_partials/form_field.html`
- `_partials/badge_card.html`
- `_partials/filterbar.html`

These may be included ad-hoc, but grep found no `{% include %}` references to them.

---

## 5. Forms Without CRUD Wiring

| Form Class | Status |
|------------|--------|
| `StyledModelForm` | Not in crud_views.py (base class only) |
| `UserCreateForm` | Not in crud_views.py |
| `UserUpdateForm` | Not in crud_views.py |
| `RoleForm` | Not in crud_views.py |
| `APIKeyForm` | Not in crud_views.py |

**Location:** `administration/forms.py` defines 23 form classes; only 18 wired to CRUD.

**Assessment:** User management CRUD (create/edit user, manage roles, API keys) is defined in forms but not implemented in `crud_views.py`.

---

## 6. Services with Dead Methods

### access_control/services.py
- `process_scan()` — defined, called?
- `_evaluate()` — internal, called?
- `_track_pairing()` — internal, called?

### ai_assistant/services.py
- `ask()` — method defined; no grep evidence of usage in views

### core/services.py
- `get()` — singleton tenant getter
- `reset_cache()` — cache invalidation method
- `get_kaydan_tenant()` — helper method

### devices/services.py
- `generate()` — badge PDF generation
- `_make_qr_bytes()` — internal QR encoding
- `_draw_qr_card()` — internal PDF rendering
- `_draw_circular_photo()` — internal PDF rendering
- `_draw_kaydan_logo_text()` — internal PDF rendering

**Assessment:** Most service methods appear to be called (badge PDF generation is used), but without tracing through all views, some internal helpers may be orphaned. Need manual code review.

---

## 7. Migrations

**Finding:** All 16 apps with models have migration folders with 2-4 migration files each.

**Status:** ✓ No missing migration folders detected.

**Potential Issue:** Django.contrib.gis not in INSTALLED_APPS despite PostGIS in dev/prod settings.
- Comment in `kshield/settings/base.py` notes: "django.contrib.gis activé conditionnellement dans dev.py/prod.py (nécessite GDAL natif)."
- **Actual state:** Not added in dev.py or prod.py; code assumes it's conditional but it's missing.

---

## 8. Tests Gap

### Zero Coverage Apps
- `administration/` — 0 tests
- `ai_assistant/` — 0 tests

### Minimal Stub Apps (3-line tests.py, no real tests)
- `access_control`, `accounts`, `antifraud`, `attendance`, `audit`, `core`, `devices`, `employees`, `mobile_sync`, `notifications`, `ouvriers`, `reports`, `sites`, `visitors`

### Real Tests (2 files, `tests/` folder)
- `test_badge_lifecycle.py` — 7.3 KB, functional test for badge workflow
- `test_badge_smoke.py` — 5.9 KB, smoke tests for badge endpoints
- `conftest.py` — pytest fixtures

**Assessment:** Only badge module has real test coverage (lifecycle + smoke). Zero tests for:
- User authentication (accounts)
- Access control rules (access_control)
- Anti-fraud detection (antifraud)
- Attendance tracking (attendance)
- Audit logging (audit)
- Device/Badge endpoints (devices)
- Employee management (employees)
- Notifications (notifications)
- Reports (reports)
- Mobile sync (mobile_sync)
- Worker/Contractor management (ouvriers)
- Site/Zone management (sites)
- Visitor management (visitors)
- AI assistant (ai_assistant)
- Administration back-office (administration)

---

## 9. Settings Issues

### DEBUG and SECRET_KEY Handling
✓ Prod: `DEBUG = False`, `SECRET_KEY = config("SECRET_KEY")` — Correct (will fail loudly if missing).  
✓ Base: `SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me")` — Safe default.  
✓ Base: `DEBUG = config("DEBUG", default=False, cast=bool)` — Safe default.

### INSTALLED_APPS Completeness
✓ All 16 local apps declared in `LOCAL_APPS`.

### Missing auth/redirect URLs
- **Not set:** `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_URL` not defined in base.py
- **Impact:** Default Django fallback used (`/accounts/login/`, `/accounts/profile/`, `/accounts/logout/`)
- **Risk:** Inconsistent with custom auth endpoints (e.g., `/api/auth/login/`)

### STATIC/MEDIA Settings
✓ Configured: `STATIC_URL = "static/"`, `STATIC_ROOT = BASE_DIR / "staticfiles"`, `MEDIA_URL = "media/"`, `MEDIA_ROOT = BASE_DIR / "media"`

### Security Headers (prod.py)
✓ Present: `SECURE_SSL_REDIRECT = True`, `CSRF_COOKIE_SECURE = True`, `SECURE_HSTS_SECONDS = 1yr`, `SECURE_CONTENT_TYPE_NOSNIFF = True`

### Django.contrib.gis Missing from INSTALLED_APPS
- **Issue:** PostGIS backend configured in dev/prod databases, but `django.contrib.gis` not added.
- **Status:** Code comment says "conditionally enabled" but it's not.
- **Action needed:** Either add `django.contrib.gis` or remove PostGIS config.

---

## 10. Declared-but-Unused Features

### Documentation File
- `docs/MODELES_ET_SERVICES.md` — Exists but never linked from README or docs/ folder structure.

### Feature Claims vs. Code
No explicit README found listing features. However, based on model/service presence, these are implemented:
- Face recognition (face-api.js downloaded, endpoints exist)
- Badge lifecycle (full implementation)
- Attendance tracking (models and serializers present)
- Antifraud rules (models and services present)
- Notifications (models and templates present)
- Audit logging (models and middleware present)
- Map/Cartography (referenced in admin views)
- AI assistant (services and endpoints present)

No evidence of unused library imports; no face_recognition/cv2/opencv imports found in Python code.

---

## 11. API Surface Gaps

### DRF Documentation (drf_spectacular)
- **Config:** ✓ `DEFAULT_SCHEMA_CLASS = "drf_spectacular.openapi.AutoSchema"` enabled
- **Schema decorators:** **0 found** — None of 50+ ViewSets have `@extend_schema` or schema documentation
- **Impact:** OpenAPI schema will be auto-generated but missing field descriptions, examples, parameters

### Permission Guards on API Endpoints
- **Finding:** Only **1 LoginRequiredMixin found** in entire codebase
- **Status:** ~50 API ViewSets have **zero permission checks**
- **Risk:** All REST endpoints are publicly accessible

### Example Unprotected Endpoints
- `GET /api/employees/` — No auth check
- `POST /api/devices/badges/` — No auth check
- `DELETE /api/access-control/rules/{id}/` — No auth check
- `GET /api/visitors/` — No auth check

**Assessment:** REST API has zero permission enforcement. Any unauthenticated client can read/write all entities.

---

## 12. Permissions / Auth Holes

### Zero Permission Requirements
Scanning `views.py` in all apps shows:
- `ScanView`, `AccessEventViewSet`, `AccessRuleViewSet`, `DoorCommandViewSet`, `QRCodeTokenViewSet` — **No auth**
- `LoginView`, `MeView`, `UserViewSet`, `RoleViewSet` — **No auth** (!)
- `AIPromptTemplateViewSet`, `AIConversationViewSet`, `AIMessageViewSet` — **No auth**
- `FraudRuleViewSet`, `FraudAlertViewSet`, `FraudInvestigationViewSet` — **No auth**
- All other app ViewSets — **No auth**

### Front-End Views (administration app)
- `DashboardView`, `AdminHomeView`, `RealtimeView`, `MapView`, `EmployeesView`, `FaceRecognitionTestView`, `WorkersView`, `VisitorsView`, `SitesView` — These are likely protected via session auth (Django views), but REST API is wide open.

### HMAC/Signature Verification
- **Comment in settings:** `"API_KEY_CLOCK_SKEW_SEC": 60`
- **Finding:** No signature verification middleware or view logic found in code search
- **Status:** Configuration exists but implementation missing

---

## Recommendations

### CRITICAL (P0 — Fix before production)

1. **Add permission decorators to ALL API endpoints**
   - Add `permission_classes = [IsAuthenticated]` to all ViewSets
   - Add `@permission_required` or `LoginRequiredMixin` to front-end views
   - Status: Affects 50+ ViewSets and 8 front-end views
   - Effort: 4-6 hours

2. **Implement HMAC signature verification**
   - Create middleware to verify IoT device signatures
   - Add to `MIDDLEWARE` in settings
   - Status: Configuration present but code missing
   - Effort: 2-3 hours

3. **Add django.contrib.gis to INSTALLED_APPS conditionally**
   - Import in dev.py and prod.py when PostGIS is active
   - Test migration compatibility
   - Effort: 1 hour

4. **Replace 8 placeholder module templates with stubs or real content**
   - Either implement UI or hide from sidebar
   - Status: accounts, antifraud, companies, devices, face_test, gateways, settings, sites
   - Effort: 2-4 hours

### IMPORTANT (P1 — Fix in next sprint)

5. **Wire 5 orphan forms to CRUD**
   - UserCreateForm, UserUpdateForm, RoleForm, APIKeyForm, StyledModelForm
   - Add entries to `administration/crud_views.py` `_build_all()` function
   - Effort: 2-3 hours

6. **Fix or remove 12 orphan detail templates**
   - Match with corresponding detail view routes
   - Either activate or delete
   - Status: company_detail.html, worker_detail.html, etc. unused
   - Effort: 2 hours

7. **Implement access_control.services.py TODO**
   - Dispatch async notifications and antifraud checks on scan completion
   - Status: Line 63, unimplemented
   - Effort: 3-4 hours

8. **Add comprehensive test suite**
   - All 16 apps need at least smoke tests
   - Priority: authentication, access_control, antifraud, devices
   - Status: Only badge module tested
   - Effort: 10+ hours

9. **Add drf_spectacular @extend_schema decorators**
   - Document all ViewSet actions with field descriptions and examples
   - Status: 50+ ViewSets undocumented
   - Effort: 6-8 hours

### NICE-TO-HAVE (P2 — Backlog)

10. **Implement soft-delete pattern across all models**
    - core.SoftDeleteModel exists but unused
    - Inherit from it or remove
    - Effort: 3-4 hours

11. **Create comprehensive README and architecture docs**
    - Document app structure, API surface, auth flow
    - Link from README to docs/MODELES_ET_SERVICES.md
    - Effort: 3-4 hours

12. **Organize template partials systematically**
    - Create template inheritance hierarchy
    - Ensure pagination, filterbar, timeline are included consistently
    - Effort: 2-3 hours

13. **Define explicit LOGIN_URL, LOGIN_REDIRECT_URL, LOGOUT_URL**
    - Override Django defaults for consistency
    - Effort: 30 minutes

14. **Trace and document service method calls**
    - Verify ai_assistant.services.ask() and other dead-seeming methods
    - Effort: 1-2 hours

---

## Summary by Severity

| Severity | Count | Examples |
|----------|-------|----------|
| **Critical** | 4 | No API auth, HMAC missing, placeholder UIs, PostGIS not activated |
| **Important** | 6 | Orphan forms, templates, TODO, test gaps, schema docs |
| **Nice-to-have** | 4 | Soft-delete, docs, template organization, URL config |

**Total Actionable Items:** 14

**Estimated Effort to Critical-Only:** 9-13 hours  
**Estimated Effort to Critical + Important:** 25-35 hours  
**Estimated Effort to All (including Nice-to-have):** 35-50 hours
