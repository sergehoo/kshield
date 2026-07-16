"""Phase 6 refonte agents locaux — Type + Heartbeat + Configuration + Log."""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0014_device_discovery"),
        ("core", "0001_initial"),
    ]

    AGENT_STATE = [
        ("installing",  "Installation"),
        ("starting",    "Démarrage"),
        ("running",     "En cours"),
        ("degraded",    "Dégradé"),
        ("stopped",     "Arrêté"),
        ("crashed",     "Crashé"),
        ("updating",    "Mise à jour"),
        ("disabled",    "Désactivé"),
        ("unreachable", "Injoignable"),
    ]

    TYPE_CODES = [
        ("rfid",         "Agent RFID"),
        ("ble",          "Agent BLE"),
        ("camera",       "Agent Caméra"),
        ("biometric",    "Agent Biométrique"),
        ("attendance",   "Agent Pointage"),
        ("mqtt",         "Agent MQTT"),
        ("sync",         "Agent Sync"),
        ("discovery",    "Agent Discovery"),
        ("monitoring",   "Agent Monitoring"),
        ("generic",      "Agent générique"),
    ]

    LOG_LEVELS = [
        ("debug",    "Debug"),
        ("info",     "Info"),
        ("warning",  "Warning"),
        ("error",    "Error"),
        ("critical", "Critical"),
    ]

    operations = [
        # ─── LocalAgentType ─────────────────────────────────────────
        migrations.CreateModel(
            name="LocalAgentType",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(
                    max_length=32, unique=True, db_index=True,
                    choices=TYPE_CODES,
                )),
                ("label", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("module_name", models.CharField(max_length=120)),
                ("capabilities", models.JSONField(default=list, blank=True)),
                ("config_schema", models.JSONField(default=dict, blank=True)),
                ("icon", models.CharField(max_length=40, blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("is_system", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["code"],
                "verbose_name": "Type d'agent local",
            },
        ),

        # ─── LocalAgentHeartbeat ────────────────────────────────────
        migrations.CreateModel(
            name="LocalAgentHeartbeat",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("sent_at", models.DateTimeField(db_index=True)),
                ("received_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("state", models.CharField(
                    max_length=16, default="running", choices=AGENT_STATE,
                )),
                ("version", models.CharField(max_length=32, blank=True)),
                ("uptime_seconds", models.BigIntegerField(default=0)),
                ("cpu_percent", models.FloatField(default=0.0)),
                ("memory_percent", models.FloatField(default=0.0)),
                ("memory_mb", models.PositiveIntegerField(default=0)),
                ("storage_percent", models.FloatField(default=0.0)),
                ("storage_free_mb", models.PositiveIntegerField(default=0)),
                ("network_latency_ms", models.PositiveIntegerField(default=0)),
                ("events_processed", models.BigIntegerField(default=0)),
                ("events_pending", models.PositiveIntegerField(default=0)),
                ("devices_connected", models.PositiveIntegerField(default=0)),
                ("devices_expected", models.PositiveIntegerField(default=0)),
                ("errors_last_hour", models.PositiveIntegerField(default=0)),
                ("sync_last_success_at", models.DateTimeField(null=True, blank=True)),
                ("recent_errors", models.JSONField(default=list, blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("agent", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="heartbeats",
                    to="devices.localagent",
                )),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="agent_heartbeats",
                    to="core.tenant",
                )),
            ],
            options={
                "ordering": ["-received_at"],
                "verbose_name": "Heartbeat d'agent",
                "indexes": [
                    models.Index(fields=["agent", "-sent_at"],
                                  name="agent_hb_ag_dt_idx"),
                    models.Index(fields=["tenant", "-received_at"],
                                  name="agent_hb_ten_dt_idx"),
                    models.Index(fields=["state", "-received_at"],
                                  name="agent_hb_st_dt_idx"),
                ],
            },
        ),

        # ─── LocalAgentConfiguration ────────────────────────────────
        migrations.CreateModel(
            name="LocalAgentConfiguration",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("payload", models.JSONField(default=dict, blank=True)),
                ("checksum", models.CharField(max_length=64, blank=True)),
                ("applied_at", models.DateTimeField(null=True, blank=True)),
                ("is_current", models.BooleanField(default=False, db_index=True)),
                ("is_draft", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("agent", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="configurations",
                    to="devices.localagent",
                )),
            ],
            options={
                "ordering": ["agent", "-version"],
                "verbose_name": "Configuration d'agent",
                "indexes": [
                    models.Index(fields=["agent", "-version"],
                                  name="agent_cf_ag_vr_idx"),
                    models.Index(fields=["agent", "is_current"],
                                  name="agent_cf_ag_cur_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["agent"],
                        condition=models.Q(is_current=True),
                        name="agent_one_current_config",
                    ),
                ],
            },
        ),

        # ─── LocalAgentLog ──────────────────────────────────────────
        migrations.CreateModel(
            name="LocalAgentLog",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("ts", models.DateTimeField(db_index=True)),
                ("level", models.CharField(
                    max_length=8, default="info", db_index=True,
                    choices=LOG_LEVELS,
                )),
                ("message", models.TextField()),
                ("context", models.JSONField(default=dict, blank=True)),
                ("source", models.CharField(max_length=64, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("agent", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="logs",
                    to="devices.localagent",
                )),
            ],
            options={
                "ordering": ["-ts"],
                "verbose_name": "Log d'agent",
                "indexes": [
                    models.Index(fields=["agent", "-ts"],  name="agent_log_ag_ts_idx"),
                    models.Index(fields=["level", "-ts"],  name="agent_log_lv_ts_idx"),
                ],
            },
        ),
    ]
