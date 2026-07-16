"""Phase 5 refonte détection équipements — DeviceDiscovery + Scan."""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0013_edge_sync"),
        ("core", "0001_initial"),
        ("sites", "0001_initial"),
    ]

    DISCOVERY_STATUS = [
        ("detected", "Détecté"), ("tested", "Testé"),
        ("adopted",  "Adopté"),  ("rejected", "Rejeté"),
        ("stale",    "Périmé"),
    ]
    DISCOVERY_PROTOCOL = [
        ("arp",     "ARP"),    ("mdns",   "mDNS / Bonjour"),
        ("ssdp",    "SSDP"),   ("onvif",  "ONVIF"),
        ("snmp",    "SNMP"),   ("nmap",   "Nmap"),
        ("ble",     "BLE"),    ("usb",    "USB / Série"),
        ("manual",  "Manuel"), ("qr",     "QR code"),
        ("token",   "Token"),  ("unknown", "Inconnu"),
    ]
    COMPATIBILITY = [
        ("compatible",   "Compatible officiel"),
        ("experimental", "Compatible (expérimental)"),
        ("unsupported",  "Non supporté (générique)"),
        ("incompatible", "Incompatible"),
        ("unknown",      "Inconnu"),
    ]

    operations = [
        # ─── DeviceDiscoveryScan ───────────────────────────────────────
        migrations.CreateModel(
            name="DeviceDiscoveryScan",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("protocols_used", models.JSONField(default=list, blank=True)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("devices_detected", models.PositiveIntegerField(default=0)),
                ("devices_new", models.PositiveIntegerField(default=0)),
                ("devices_updated", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(
                    max_length=12, default="running", db_index=True,
                    choices=[
                        ("running", "En cours"),
                        ("succeeded", "Terminé"),
                        ("failed", "Échec"),
                    ],
                )),
                ("error", models.TextField(blank=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="discovery_scans",
                    to="core.tenant",
                )),
                ("gateway", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="discovery_scans",
                    to="devices.localagent",
                )),
                ("site", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="discovery_scans",
                    to="sites.site",
                )),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Session de scan discovery",
                "indexes": [
                    models.Index(fields=["tenant", "-created_at"],
                                  name="discovery_scan_ten_dt_idx"),
                    models.Index(fields=["gateway", "-created_at"],
                                  name="discovery_scan_gw_dt_idx"),
                ],
            },
        ),

        # ─── DeviceDiscovery ─────────────────────────────────────────
        migrations.CreateModel(
            name="DeviceDiscovery",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("mac_address", models.CharField(max_length=17, blank=True, db_index=True)),
                ("ip_address", models.GenericIPAddressField(null=True, blank=True, db_index=True)),
                ("hostname", models.CharField(max_length=120, blank=True)),
                ("serial_number", models.CharField(max_length=64, blank=True, db_index=True)),
                ("vendor", models.CharField(max_length=64, blank=True, db_index=True)),
                ("model", models.CharField(max_length=120, blank=True)),
                ("device_type", models.CharField(max_length=32, blank=True)),
                ("firmware_version", models.CharField(max_length=40, blank=True)),
                ("protocols_supported", models.JSONField(default=list, blank=True)),
                ("ports_open", models.JSONField(default=list, blank=True)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("signal_strength", models.IntegerField(null=True, blank=True)),
                ("status", models.CharField(
                    max_length=12, default="detected", db_index=True,
                    choices=DISCOVERY_STATUS,
                )),
                ("detected_via", models.CharField(
                    max_length=12, default="unknown",
                    choices=DISCOVERY_PROTOCOL,
                )),
                ("compatibility", models.CharField(
                    max_length=16, default="unknown",
                    choices=COMPATIBILITY,
                )),
                ("suggested_driver", models.CharField(max_length=40, blank=True)),
                ("last_test_at", models.DateTimeField(null=True, blank=True)),
                ("last_test_success", models.BooleanField(default=False)),
                ("last_test_error", models.TextField(blank=True)),
                ("last_test_response", models.JSONField(default=dict, blank=True)),
                ("adopted_at", models.DateTimeField(null=True, blank=True)),
                ("adopted_by", models.CharField(max_length=200, blank=True)),
                ("rejected_at", models.DateTimeField(null=True, blank=True)),
                ("rejected_reason", models.CharField(max_length=240, blank=True)),
                ("times_seen", models.PositiveIntegerField(default=1)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("raw_payload", models.JSONField(default=dict, blank=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="discoveries",
                    to="core.tenant",
                )),
                ("scan", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="discoveries",
                    to="devices.devicediscoveryscan",
                )),
                ("gateway", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="discoveries",
                    to="devices.localagent",
                )),
                ("site", models.ForeignKey(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="discoveries",
                    to="sites.site",
                )),
                ("adopted_device", models.OneToOneField(
                    null=True, blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="discovery_origin",
                    to="devices.device",
                )),
            ],
            options={
                "ordering": ["-last_seen_at"],
                "verbose_name": "Équipement découvert",
                "verbose_name_plural": "Équipements découverts",
                "indexes": [
                    models.Index(fields=["tenant", "status", "-last_seen_at"],
                                  name="discovery_ten_st_dt_idx"),
                    models.Index(fields=["gateway", "status"],
                                  name="discovery_gw_st_idx"),
                    models.Index(fields=["compatibility", "status"],
                                  name="discovery_cp_st_idx"),
                    models.Index(fields=["vendor", "device_type"],
                                  name="discovery_vd_dt_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["tenant", "mac_address"],
                        condition=~models.Q(mac_address=""),
                        name="discovery_unique_mac_per_tenant",
                    ),
                ],
            },
        ),
    ]
