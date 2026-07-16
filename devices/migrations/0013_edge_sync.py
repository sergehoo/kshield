"""Phase 4 refonte Edge Sync — batches + items + conflits."""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0012_badge_lifecycle"),
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ─── EdgeSyncBatch ───────────────────────────────────────────
        migrations.CreateModel(
            name="EdgeSyncBatch",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("batch_id", models.CharField(max_length=64, db_index=True)),
                ("direction", models.CharField(
                    max_length=10, db_index=True,
                    choices=[
                        ("upload",   "Edge → Cloud (upload)"),
                        ("download", "Cloud → Edge (download)"),
                    ],
                )),
                ("status", models.CharField(
                    max_length=16, default="pending", db_index=True,
                    choices=[
                        ("pending",    "En attente"),
                        ("uploading",  "Upload en cours"),
                        ("processing", "Traitement serveur"),
                        ("completed",  "Complété"),
                        ("partial",    "Partiel (avec erreurs)"),
                        ("failed",     "Échec définitif"),
                        ("cancelled",  "Annulé"),
                    ],
                )),
                ("priority", models.CharField(
                    max_length=10, default="normal", db_index=True,
                    choices=[
                        ("low",      "Basse"),
                        ("normal",   "Normale"),
                        ("high",     "Haute"),
                        ("critical", "Critique"),
                    ],
                )),
                ("items_declared",   models.PositiveIntegerField(default=0)),
                ("items_uploaded",   models.PositiveIntegerField(default=0)),
                ("items_processed",  models.PositiveIntegerField(default=0)),
                ("items_succeeded",  models.PositiveIntegerField(default=0)),
                ("items_failed",     models.PositiveIntegerField(default=0)),
                ("items_conflicted", models.PositiveIntegerField(default=0)),
                ("checksum_algorithm", models.CharField(max_length=16, default="sha256")),
                ("checksum_declared", models.CharField(max_length=128, blank=True)),
                ("checksum_computed", models.CharField(max_length=128, blank=True)),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("upload_finished_at", models.DateTimeField(null=True, blank=True)),
                ("processed_at", models.DateTimeField(null=True, blank=True)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("resume_from_offset", models.PositiveIntegerField(default=0)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("compression", models.CharField(max_length=16, blank=True)),
                ("encryption", models.CharField(max_length=32, blank=True)),
                ("payload_size_bytes", models.BigIntegerField(default=0)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("gateway", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sync_batches",
                    to="devices.localagent",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sync_batches",
                    to="core.tenant",
                )),
            ],
            options={
                "ordering": ["-started_at"],
                "verbose_name": "Batch de synchronisation Edge",
                "indexes": [
                    models.Index(fields=["gateway", "-started_at"],       name="edgesync_bt_gw_dt_idx"),
                    models.Index(fields=["tenant", "status", "-started_at"], name="edgesync_bt_ts_dt_idx"),
                    models.Index(fields=["priority", "status"],           name="edgesync_bt_pr_st_idx"),
                    models.Index(fields=["direction", "status"],          name="edgesync_bt_dr_st_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["gateway", "batch_id"],
                        name="edgesync_batch_id_unique_per_gw",
                    ),
                ],
            },
        ),

        # ─── EdgeSyncItem ────────────────────────────────────────────
        migrations.CreateModel(
            name="EdgeSyncItem",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("entity_type", models.CharField(max_length=32, db_index=True)),
                ("entity_key", models.CharField(max_length=128, db_index=True)),
                ("entity_version", models.PositiveIntegerField(default=1)),
                ("payload", models.JSONField(default=dict, blank=True)),
                ("payload_hash", models.CharField(max_length=64, blank=True)),
                ("status", models.CharField(
                    max_length=12, default="pending", db_index=True,
                    choices=[
                        ("pending",   "En attente"),
                        ("succeeded", "Traité avec succès"),
                        ("failed",    "Erreur"),
                        ("conflict",  "Conflit détecté"),
                        ("skipped",   "Ignoré (dédup)"),
                    ],
                )),
                ("error", models.TextField(blank=True)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(null=True, blank=True)),
                ("resolved_object_id", models.CharField(max_length=64, blank=True)),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="items",
                    to="devices.edgesyncbatch",
                )),
            ],
            options={
                "ordering": ["batch", "received_at"],
                "verbose_name": "Item de synchronisation",
                "indexes": [
                    models.Index(fields=["batch", "status"],             name="edgesync_it_bt_st_idx"),
                    models.Index(fields=["entity_type", "entity_key"],   name="edgesync_it_et_ek_idx"),
                    models.Index(fields=["payload_hash"],                name="edgesync_it_ph_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["batch", "entity_type", "entity_key"],
                        name="edgesync_item_dedup_per_batch",
                    ),
                ],
            },
        ),

        # ─── EdgeSyncConflict ────────────────────────────────────────
        migrations.CreateModel(
            name="EdgeSyncConflict",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entity_type", models.CharField(max_length=32, db_index=True)),
                ("entity_key", models.CharField(max_length=128, db_index=True)),
                ("edge_payload", models.JSONField(default=dict, blank=True)),
                ("cloud_payload", models.JSONField(default=dict, blank=True)),
                ("edge_version", models.PositiveIntegerField(default=0)),
                ("cloud_version", models.PositiveIntegerField(default=0)),
                ("edge_updated_at", models.DateTimeField(null=True, blank=True)),
                ("cloud_updated_at", models.DateTimeField(null=True, blank=True)),
                ("resolution", models.CharField(
                    max_length=16, default="pending", db_index=True,
                    choices=[
                        ("pending",    "En attente"),
                        ("cloud_wins", "Cloud a raison"),
                        ("edge_wins",  "Edge a raison"),
                        ("merge",      "Fusion"),
                        ("ignore",     "Ignoré"),
                        ("escalated",  "Escaladé"),
                    ],
                )),
                ("resolution_notes", models.TextField(blank=True)),
                ("resolved_at", models.DateTimeField(null=True, blank=True)),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="conflicts",
                    to="devices.edgesyncbatch",
                )),
                ("item", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="conflicts",
                    to="devices.edgesyncitem",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sync_conflicts",
                    to="core.tenant",
                )),
                ("resolved_by", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="sync_conflicts_resolved",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Conflit de synchronisation",
                "indexes": [
                    models.Index(fields=["resolution", "-created_at"],  name="edgesync_cf_rs_dt_idx"),
                    models.Index(fields=["entity_type", "entity_key"],  name="edgesync_cf_et_ek_idx"),
                    models.Index(fields=["tenant", "resolution"],       name="edgesync_cf_tn_rs_idx"),
                ],
            },
        ),
    ]
