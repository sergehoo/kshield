"""Phase 3 refonte badges — 12 états + 8 holder_kinds + BadgeAssignment
+ BadgeLifecycleEvent.

Migration manuelle pour :
  1. Étendre Badge.STATUS_CHOICES (8 → 12 états)
  2. Étendre Badge.HOLDER_KIND_CHOICES (3 → 8 types)
  3. Faire évoluer BadgeAssignment sans perdre l'historique de 0002
  4. Créer BadgeLifecycleEvent (transitions d'état)
"""
import uuid

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

        # ─── 3. Évolution de BadgeAssignment sans perte de données ──
        # La table existe depuis 0002. On conserve sa PK BigAutoField et ses
        # champs d'audit, puis on l'enrichit avec le nouveau cycle de vie.
        migrations.AlterModelOptions(
            name="badgeassignment",
            options={
                "ordering": ["-assigned_at"],
                "verbose_name": "Attribution de badge",
                "verbose_name_plural": "Attributions de badges",
            },
        ),
        migrations.RemoveIndex(
            model_name="badgeassignment",
            name="devices_bad_badge_i_7afb11_idx",
        ),
        migrations.RemoveIndex(
            model_name="badgeassignment",
            name="devices_bad_holder__16809b_idx",
        ),
        migrations.RenameField(
            model_name="badgeassignment",
            old_name="released_at",
            new_name="closed_at",
        ),
        migrations.RenameField(
            model_name="badgeassignment",
            old_name="released_by",
            new_name="closed_by",
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="holder_kind",
            field=models.CharField(max_length=16, choices=HOLDER_KIND_CHOICES),
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="holder_object_id",
            field=models.PositiveBigIntegerField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="holder_label",
            field=models.CharField(
                max_length=240,
                help_text="Nom complet du titulaire au moment de l'attribution.",
            ),
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="assigned_at",
            field=models.DateTimeField(
                auto_now_add=True,
                db_index=True,
                help_text="Date d'attribution (immuable).",
            ),
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="assigned_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text="Utilisateur qui a créé l'attribution.",
            ),
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="closed_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                db_index=True,
                help_text="NULL = active. Non-NULL = fermée.",
            ),
        ),
        migrations.AlterField(
            model_name="badgeassignment",
            name="closed_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="tenant",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="badge_assignments",
                to="core.tenant",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="holder_content_type",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="site",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="badge_assignments",
                to="sites.site",
                help_text="Site principal — le badge n'est actif que sur ce site.",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="access_level",
            field=models.CharField(
                max_length=16,
                default="basic",
                choices=[
                    ("none", "Aucun (badge visiteur simple)"),
                    ("basic", "Basique"),
                    ("standard", "Standard"),
                    ("elevated", "Élevé (superviseur)"),
                    ("critical", "Critique (direction/sécurité)"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="activated_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Date à partir de laquelle le badge peut être utilisé.",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="expires_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                db_index=True,
                help_text="Fin de validité — le badge passe auto en state expired.",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="time_window_start",
            field=models.TimeField(
                null=True,
                blank=True,
                help_text="Heure de début autorisée dans la journée (ex: 06:00).",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="time_window_end",
            field=models.TimeField(
                null=True,
                blank=True,
                help_text="Heure de fin autorisée dans la journée (ex: 22:00).",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="allowed_weekdays",
            field=models.CharField(
                max_length=20,
                blank=True,
                default="",
                help_text='Jours autorisés séparés par virgule (ex: "0,1,2,3,4" = lun-ven, 0=lundi, 6=dimanche). Vide = tous les jours.',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="is_permanent",
            field=models.BooleanField(
                default=False,
                help_text="True : attribution permanente sans expires_at. False : attribution temporaire (dates obligatoires).",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="reason",
            field=models.CharField(
                max_length=240,
                blank=True,
                default="",
                help_text='Motif d\'attribution : "Mission chantier Riviera 2026-Q3", "Visiteur ENT-CI", etc.',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="validated_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                help_text="Responsable qui a validé cette attribution (workflow d'approbation pour niveaux élevés).",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="close_reason",
            field=models.CharField(
                max_length=16,
                blank=True,
                default="",
                choices=[
                    ("unassigned", "Désaffecté volontairement"),
                    ("expired", "Expiré (fin de validité)"),
                    ("lost", "Perdu"),
                    ("stolen", "Volé"),
                    ("suspended", "Suspendu (temporaire)"),
                    ("revoked", "Révoqué (sanction)"),
                    ("holder_left", "Titulaire parti (démission/fin visite)"),
                    ("destroyed", "Badge détruit"),
                    ("replaced", "Remplacé par un nouveau badge"),
                    ("archived", "Archivé (RGPD)"),
                ],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="close_notes",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="metadata",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Champs additionnels (n° véhicule, catégorie ressource, etc.)",
            ),
        ),
        migrations.AddField(
            model_name="badgeassignment",
            name="zones",
            field=models.ManyToManyField(
                blank=True,
                related_name="badge_assignments",
                to="sites.zone",
                help_text="Zones autorisées (vide = toutes les zones du site).",
            ),
        ),
        migrations.RunPython(migrate_legacy_assignments, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="badgeassignment",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="badge_assignments",
                to="core.tenant",
            ),
        ),
        migrations.RemoveField(
            model_name="badgeassignment",
            name="visit_request",
        ),
        migrations.AddIndex(
            model_name="badgeassignment",
            index=models.Index(
                fields=["badge", "-assigned_at"],
                name="badge_assign_bg_dt_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="badgeassignment",
            index=models.Index(
                fields=["tenant", "-assigned_at"],
                name="badge_assign_ten_dt_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="badgeassignment",
            index=models.Index(
                fields=["holder_kind", "closed_at"],
                name="badge_assign_hk_cl_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="badgeassignment",
            index=models.Index(
                fields=["site", "closed_at"],
                name="badge_assign_st_cl_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="badgeassignment",
            index=models.Index(
                fields=["expires_at"],
                name="badge_assign_exp_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="badgeassignment",
            constraint=models.UniqueConstraint(
                fields=["badge"],
                condition=models.Q(closed_at__isnull=True),
                name="badge_one_active_assignment",
            ),
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
