"""Migration : indexes composites pour performance dashboards + anti-fraude.

Cible les requêtes les plus fréquentes :
  - Punch : filtres par (site, date) + (employee, date) pour pointage RH
  - AttendanceDay : (date, site) pour vues calendrier
  - BLEPresencePing : (helmet, timestamp DESC) pour timeline temps réel
  - Roster : (date, site) pour planning
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0003_face_sighting_confirmation"),
    ]

    operations = [
        # ───── Punch : pointage RFID (table la plus volumineuse) ─────
        migrations.AddIndex(
            model_name="punch",
            index=models.Index(
                fields=["site", "-timestamp"],
                name="punch_site_ts_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="punch",
            index=models.Index(
                fields=["holder_kind", "holder_object_id", "-timestamp"],
                name="punch_holder_ts_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="punch",
            index=models.Index(
                fields=["type", "-timestamp"],
                name="punch_type_ts_idx",
            ),
        ),

        # ───── AttendanceDay : calendrier + agrégations ─────
        migrations.AddIndex(
            model_name="attendanceday",
            index=models.Index(
                fields=["date", "site"],
                name="attday_date_site_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="attendanceday",
            index=models.Index(
                fields=["status", "date"],
                name="attday_status_date_idx",
            ),
        ),

        # ───── BLEPresencePing : très haute volumétrie ─────
        migrations.AddIndex(
            model_name="blepresenceping",
            index=models.Index(
                fields=["helmet", "-timestamp"],
                name="ble_ping_helmet_ts_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="blepresenceping",
            index=models.Index(
                fields=["zone", "-timestamp"],
                name="ble_ping_zone_ts_idx",
            ),
        ),

        # ───── Roster : planning par site ─────
        migrations.AddIndex(
            model_name="roster",
            index=models.Index(
                fields=["date", "site"],
                name="roster_date_site_idx",
            ),
        ),
    ]
