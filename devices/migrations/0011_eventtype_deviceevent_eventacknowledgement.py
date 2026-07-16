"""Phase 1 refonte événements — modèles EventType + DeviceEvent + Ack.

Migration créée manuellement pour éviter les dépendances circulaires
avec access_control (OneToOneField) et sites (FK checkpoint/zone).
"""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0010_gatewaytarget"),
        ("core", "0001_initial"),
        ("sites", "0001_initial"),
        ("access_control", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ─── EventType — nomenclature paramétrable ────────────────────
        migrations.CreateModel(
            name="EventType",
            fields=[
                ("id", models.AutoField(
                    auto_created=True, primary_key=True, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(
                    max_length=64, unique=True, db_index=True,
                )),
                ("category", models.CharField(
                    max_length=16, db_index=True,
                    choices=[
                        ("access",     "Contrôle d'accès"),
                        ("attendance", "Pointage"),
                        ("rfid",       "RFID / NFC"),
                        ("ble",        "BLE / Casques"),
                        ("device",     "Équipements"),
                        ("gateway",    "Gateway & Agents"),
                        ("security",   "Sécurité"),
                        ("system",     "Système"),
                    ],
                )),
                ("label", models.CharField(max_length=140)),
                ("description", models.TextField(blank=True)),
                ("severity_default", models.CharField(
                    max_length=12, default="info",
                    choices=[
                        ("info", "Information"),
                        ("warning", "Avertissement"),
                        ("critical", "Critique"),
                        ("emergency", "Urgence"),
                    ],
                )),
                ("result_default", models.CharField(
                    max_length=12, default="neutral",
                    choices=[
                        ("granted", "Autorisé"),
                        ("denied", "Refusé"),
                        ("pending", "En attente"),
                        ("anomaly", "Anomalie"),
                        ("alert", "Alerte"),
                        ("neutral", "Neutre"),
                    ],
                )),
                ("icon", models.CharField(max_length=40, blank=True)),
                ("color", models.CharField(max_length=20, blank=True)),
                ("triggers_alert", models.BooleanField(default=False)),
                ("requires_ack", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["category", "code"],
                "verbose_name": "Type d'événement",
                "verbose_name_plural": "Types d'événements",
                "indexes": [
                    models.Index(
                        fields=["category", "is_active"],
                        name="devevent_type_cat_active_idx",
                    ),
                    models.Index(
                        fields=["severity_default"],
                        name="devevent_type_sev_idx",
                    ),
                ],
            },
        ),

        # ─── DeviceEvent — événement technique unifié ────────────────
        migrations.CreateModel(
            name="DeviceEvent",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("holder_kind", models.CharField(
                    max_length=12, blank=True,
                    choices=[
                        ("employee", "Employé"),
                        ("worker",   "Ouvrier"),
                        ("visitor",  "Visiteur"),
                        ("agent",    "Agent"),
                        ("vehicle",  "Véhicule"),
                        ("unknown",  "Inconnu"),
                    ],
                )),
                ("holder_ref", models.CharField(max_length=64, blank=True)),
                ("badge_uid", models.CharField(
                    max_length=64, blank=True, db_index=True,
                )),
                ("helmet_uid", models.CharField(
                    max_length=64, blank=True, db_index=True,
                )),
                ("result", models.CharField(
                    max_length=12, default="neutral", db_index=True,
                    choices=[
                        ("granted", "Autorisé"), ("denied", "Refusé"),
                        ("pending", "En attente"), ("anomaly", "Anomalie"),
                        ("alert", "Alerte"), ("neutral", "Neutre"),
                    ],
                )),
                ("severity", models.CharField(
                    max_length=12, default="info", db_index=True,
                    choices=[
                        ("info", "Information"),
                        ("warning", "Avertissement"),
                        ("critical", "Critique"),
                        ("emergency", "Urgence"),
                    ],
                )),
                ("occurred_at", models.DateTimeField(db_index=True)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("transmission_mode", models.CharField(
                    max_length=16, default="realtime_cloud", db_index=True,
                    choices=[
                        ("realtime_cloud", "Temps réel Cloud"),
                        ("gateway_local", "Gateway locale"),
                        ("deferred_sync", "Synchronisation différée"),
                        ("offline", "Événement offline"),
                    ],
                )),
                ("is_offline", models.BooleanField(default=False, db_index=True)),
                ("is_synced", models.BooleanField(default=True, db_index=True)),
                ("sync_batch_id", models.CharField(
                    max_length=64, blank=True, db_index=True,
                )),
                ("driver_code", models.CharField(max_length=40, blank=True)),
                ("payload", models.JSONField(default=dict, blank=True)),
                ("message", models.TextField(blank=True)),
                ("photo_url", models.URLField(blank=True)),
                ("idempotency_key", models.CharField(
                    max_length=64, blank=True, db_index=True,
                )),
                # FK
                ("event_type", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="events",
                    to="devices.eventtype",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="device_events",
                    to="core.tenant",
                )),
                ("site", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="device_events",
                    to="sites.site",
                )),
                ("zone", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="device_events",
                    to="sites.zone",
                )),
                ("checkpoint", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="device_events",
                    to="sites.checkpoint",
                )),
                ("device", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="tech_events",
                    to="devices.device",
                )),
                ("gateway", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="events_via_gateway",
                    to="devices.localagent",
                )),
                ("agent", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="events_local",
                    to="devices.localagent",
                )),
                ("access_event", models.OneToOneField(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="tech_event",
                    to="access_control.accessevent",
                )),
            ],
            options={
                "ordering": ["-occurred_at"],
                "verbose_name": "Événement technique",
                "verbose_name_plural": "Événements techniques",
                "indexes": [
                    models.Index(fields=["tenant", "-occurred_at"],       name="dev_ev_tenant_dt_idx"),
                    models.Index(fields=["site", "-occurred_at"],         name="dev_ev_site_dt_idx"),
                    models.Index(fields=["event_type", "-occurred_at"],   name="dev_ev_type_dt_idx"),
                    models.Index(fields=["severity", "-occurred_at"],     name="dev_ev_sev_dt_idx"),
                    models.Index(fields=["result", "-occurred_at"],       name="dev_ev_res_dt_idx"),
                    models.Index(fields=["gateway", "-occurred_at"],      name="dev_ev_gw_dt_idx"),
                    models.Index(fields=["device", "-occurred_at"],       name="dev_ev_dev_dt_idx"),
                    models.Index(fields=["is_offline", "-occurred_at"],   name="dev_ev_off_dt_idx"),
                    models.Index(fields=["is_synced", "-occurred_at"],    name="dev_ev_sync_dt_idx"),
                    models.Index(fields=["transmission_mode", "-occurred_at"], name="dev_ev_mode_dt_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["tenant", "idempotency_key"],
                        condition=~models.Q(idempotency_key=""),
                        name="devevent_idempotency_unique",
                    ),
                ],
            },
        ),

        # ─── EventAcknowledgement — traçabilité immutable ────────────
        migrations.CreateModel(
            name="EventAcknowledgement",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("action", models.CharField(
                    max_length=16, db_index=True,
                    choices=[
                        ("acknowledge", "Acquittement"),
                        ("resolve",     "Résolution"),
                        ("escalate",    "Escalade"),
                        ("comment",     "Commentaire"),
                        ("evidence",    "Preuve jointe"),
                        ("reopen",      "Réouverture"),
                    ],
                )),
                ("notes", models.TextField(blank=True)),
                ("evidence_url", models.URLField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("event", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="acknowledgements",
                    to="devices.deviceevent",
                )),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="event_acks",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Acquittement d'événement",
                "indexes": [
                    models.Index(fields=["event", "-created_at"],  name="dev_ev_ack_evt_dt_idx"),
                    models.Index(fields=["action", "-created_at"], name="dev_ev_ack_act_dt_idx"),
                ],
            },
        ),
    ]
