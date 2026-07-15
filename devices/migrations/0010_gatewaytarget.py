"""Crée le modèle GatewayTarget (Phase 3 — équipements vendors)."""
import uuid

import django.db.models.deletion
from django.db import migrations, models

import core.fields


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0009_alter_localagent_hmac_secret"),
    ]

    operations = [
        migrations.CreateModel(
            name="GatewayTarget",
            fields=[
                ("id", models.UUIDField(
                    default=uuid.uuid4, editable=False,
                    primary_key=True, serialize=False,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(
                    max_length=120,
                    help_text='Nom convivial, ex. "Portail entrée principale".',
                )),
                ("vendor", models.CharField(
                    max_length=24, db_index=True,
                    choices=[
                        ("zkteco",    "ZKTeco (Push HTTP)"),
                        ("hikvision", "Hikvision (ISAPI)"),
                        ("suprema",   "Suprema (BioStar 2 REST)"),
                        ("hid",       "HID Global (VertX)"),
                        ("dahua",     "Dahua (CGI)"),
                        ("axis",      "Axis (VAPIX)"),
                        ("onvif",     "ONVIF générique"),
                        ("generic",   "Générique (custom)"),
                    ],
                )),
                ("ip", models.GenericIPAddressField()),
                ("port", models.PositiveIntegerField(default=0)),
                ("username", models.CharField(max_length=120, blank=True)),
                ("password", core.fields.EncryptedCharField(
                    max_length=512, blank=True,
                    help_text="Password vendor (stocké chiffré Fernet).",
                )),
                ("mac", models.CharField(max_length=17, blank=True)),
                ("model", models.CharField(max_length=80, blank=True)),
                ("firmware", models.CharField(max_length=40, blank=True)),
                ("serial_number", models.CharField(
                    max_length=64, blank=True, db_index=True,
                )),
                ("connected", models.BooleanField(default=False)),
                ("last_seen_at", models.DateTimeField(null=True, blank=True)),
                ("events_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("extra", models.JSONField(default=dict, blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("gateway", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="targets",
                    to="devices.localagent",
                )),
            ],
            options={
                "ordering": ["gateway", "vendor", "label"],
                "indexes": [
                    models.Index(fields=["gateway", "enabled"],
                                  name="devices_gt_gw_en_idx"),
                    models.Index(fields=["vendor", "enabled"],
                                  name="devices_gt_ven_en_idx"),
                ],
                "unique_together": {("gateway", "ip", "port")},
            },
        ),
    ]
