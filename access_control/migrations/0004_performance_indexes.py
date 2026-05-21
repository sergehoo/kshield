"""Migration : indexes pour AccessEvent (table la + queryée par les dashboards)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0003_initial"),
    ]

    operations = [
        # Dashboards realtime : SELECT WHERE site=X AND timestamp > now()-1h ORDER BY timestamp DESC
        migrations.AddIndex(
            model_name="accessevent",
            index=models.Index(
                fields=["site", "-timestamp"],
                name="acc_evt_site_ts_idx",
            ),
        ),
        # Anti-fraude : SELECT WHERE badge_uid=X AND timestamp > today GROUP BY holder_kind
        migrations.AddIndex(
            model_name="accessevent",
            index=models.Index(
                fields=["badge_uid", "-timestamp"],
                name="acc_evt_badge_ts_idx",
            ),
        ),
        # Anti-fraude GHOST_HELMET : SELECT WHERE helmet_uid != '' AND badge_uid = ''
        migrations.AddIndex(
            model_name="accessevent",
            index=models.Index(
                fields=["helmet_uid", "-timestamp"],
                name="acc_evt_helmet_ts_idx",
            ),
        ),
        # Filtres par décision (granted/denied/review) + période
        migrations.AddIndex(
            model_name="accessevent",
            index=models.Index(
                fields=["decision", "-timestamp"],
                name="acc_evt_decision_ts_idx",
            ),
        ),
    ]
