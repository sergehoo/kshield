"""Phase 3 refonte badges — 12 états + 8 holder_kinds + BadgeAssignment
+ BadgeLifecycleEvent.

Migration manuelle pour :
  1. Étendre Badge.STATUS_CHOICES (8 → 12 états)
  2. Étendre Badge.HOLDER_KIND_CHOICES (3 → 8 types)
  3. Créer BadgeAssignment (historique immutable)
  4. Créer BadgeLifecycleEvent (transitions d'état)
"""
import uuid

import django.contrib.contenttypes.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_legacy_assignments(apps, schema_editor):
    """Complète les anciennes affectations sans perdre leur historique."""
    BadgeAssignment = apps.get_model("devices", "BadgeAssignment")
    database = schema_editor.connection.alias
    latest_open_at = {}

    assignments = (
        BadgeAssignment.objects.using(database)
        .select_related("badge")
        .order_by("badge_id", "-assigned_at", "-pk")
    )
    for assignment in assignments.iterator():
        update_fields = []

        assignment.tenant_id = assignment.badge.tenant_id
        update_fields.append("tenant")

        if assignment.visit_request_id and not assignment.reason:
            assignment.reason = f"Visite #{assignment.visit_request_id}"
            update_fields.append("reason")

        if assignment.closed_at is not None:
            if not assignment.close_reason:
                assignment.close_reason = "unassigned"
                update_fields.append("close_reason")
        elif assignment.badge_id in latest_open_at:
            assignment.closed_at = latest_open_at[assignment.badge_id]
            assignment.close_reason = "replaced"
            update_fields.extend(["closed_at", "close_reason"])
        else:
            latest_open_at[assignment.badge_id] = assignment.assigned_at

        assignment.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0011_eventtype_deviceevent_eventacknowledgement"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0001_initial"),
        ("sites", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    STATUS_CHOICES = [
        ("available",  "Disponible (en pool)"),
        ("enrolling",  "En cours d'enrôlement"),
        ("assigned",   "Attribué (pas encore utilisé)"),
        ("active",     "Actif"),
        ("suspended",  "Suspendu"),
        ("expired",    "Expiré"),
        ("lost",       "Perdu"),
        ("stolen",     "Volé"),
        ("disabled",   "Désactivé"),
        ("revoked",    "Révoqué (interdit d'usage)"),
        ("destroyed",  "Détruit physiquement"),
        ("archived",   "Archivé (RGPD, conservé pour audit)"),
    ]

    HOLDER_KIND_CHOICES = [
        ("employee",    "Employé"),
        ("worker",      "Ouvrier"),
        ("visitor",     "Visiteur"),
        ("agent",       "Agent sécurité"),
        ("contractor",  "Prestataire externe"),
        ("vehicle",     "Véhicule"),
        ("equipment",   "Équipement / matériel"),
        ("resource",    "Ressource temporaire"),
    ]

    operations = [
        # ─── 1. Étend Badge.status (8 → 12 choix) ───────────────────
        migrations.AlterField(
            model_name="badge",
            name="status",
            field=models.CharField(
                max_length=12,
                choices=STATUS_CHOICES,
                default="active",
            ),
        ),

        # ─── 2. Étend Badge.holder_kind (3 → 8 choix) ───────────────
        migrations.AlterField(
            model_name="badge",
            name="holder_kind",
            field=models.CharField(
                max_length=16,
                choices=HOLDER_KIND_CHOICES,
                blank=True,
            ),
        ),

        # ─── 3. BadgeAssignment (historique immutable) ──────────────
        migrations.CreateModel(
            name="BadgeAssignment",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("holder_kind", models.CharField(
                    max_length=16, choices=HOLDER_KIND_CHOICES,
                )),
                ("holder_object_id", models.PositiveBigIntegerField(
                    null=True, blank=True,
                )),
                ("holder_label", models.CharField(max_length=200)),
                ("access_level", models.CharField(
                    max_length=16, default="basic",
                    choices=[
                        ("none",     "Aucun"),
                        ("basic",    "Basique"),
                        ("standard", "Standard"),
                        ("elevated", "Élevé"),
                        ("critical", "Critique"),
                    ],
                )),
                ("assigned_at", models.DateTimeField(
                    auto_now_add=True, db_index=True,
                )),
                ("activated_at", models.DateTimeField(null=True, blank=True)),
                ("expires_at", models.DateTimeField(
                    null=True, blank=True, db_index=True,
                )),
                ("time_window_start", models.TimeField(null=True, blank=True)),
                ("time_window_end", models.TimeField(null=True, blank=True)),
                ("allowed_weekdays", models.CharField(max_length=20, blank=True)),
                ("is_permanent", models.BooleanField(default=False)),
                ("reason", models.CharField(max_length=240, blank=True)),
                ("closed_at", models.DateTimeField(
                    null=True, blank=True, db_index=True,
                )),
                ("close_reason", models.CharField(max_length=16, blank=True)),
                ("close_notes", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("badge", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="assignments",
                    to="devices.badge",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="badge_assignments",
                    to="core.tenant",
                )),
                ("holder_content_type", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to="contenttypes.contenttype",
                )),
                ("site", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="badge_assignments",
                    to="sites.site",
                )),
                ("assigned_by", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("validated_by", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("closed_by", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("zones", models.ManyToManyField(
                    blank=True,
                    related_name="badge_assignments",
                    to="sites.zone",
                )),
            ],
            options={
                "ordering": ["-assigned_at"],
                "verbose_name": "Attribution de badge",
                "verbose_name_plural": "Attributions de badges",
                "indexes": [
                    models.Index(fields=["badge", "-assigned_at"],
                                  name="badge_assign_bg_dt_idx"),
                    models.Index(fields=["tenant", "-assigned_at"],
                                  name="badge_assign_ten_dt_idx"),
                    models.Index(fields=["holder_kind", "closed_at"],
                                  name="badge_assign_hk_cl_idx"),
                    models.Index(fields=["site", "closed_at"],
                                  name="badge_assign_st_cl_idx"),
                    models.Index(fields=["expires_at"],
                                  name="badge_assign_exp_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["badge"],
                        condition=models.Q(closed_at__isnull=True),
                        name="badge_one_active_assignment",
                    ),
                ],
            },
        ),

        # ─── 4. BadgeLifecycleEvent (transitions immuables) ─────────
        migrations.CreateModel(
            name="BadgeLifecycleEvent",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("from_status", models.CharField(max_length=16, blank=True)),
                ("to_status", models.CharField(max_length=16)),
                ("reason", models.CharField(max_length=240, blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(
                    auto_now_add=True, db_index=True,
                )),
                ("badge", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="lifecycle_events",
                    to="devices.badge",
                )),
                ("performed_by", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Événement cycle de vie badge",
                "indexes": [
                    models.Index(fields=["badge", "-created_at"],
                                  name="badge_lc_bg_dt_idx"),
                    models.Index(fields=["to_status", "-created_at"],
                                  name="badge_lc_st_dt_idx"),
                ],
            },
        ),
    ]
