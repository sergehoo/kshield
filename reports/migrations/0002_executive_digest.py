"""Migration : modèle ExecutiveDigest (résumé IA hebdomadaire)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0001_initial"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExecutiveDigest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period", models.CharField(max_length=12, default="weekly", choices=[
                    ("weekly", "Hebdomadaire"),
                    ("monthly", "Mensuel"),
                    ("quarterly", "Trimestriel"),
                ])),
                ("period_start", models.DateField(db_index=True)),
                ("period_end", models.DateField()),
                ("status", models.CharField(max_length=12, default="queued", choices=[
                    ("queued", "En file"), ("generating", "Génération"),
                    ("ready", "Prêt"), ("failed", "Échec"),
                ])),
                ("raw_metrics", models.JSONField(default=dict, blank=True)),
                ("title", models.CharField(max_length=240, blank=True)),
                ("executive_summary", models.TextField(blank=True)),
                ("top_alerts", models.JSONField(default=list, blank=True)),
                ("kpi_deltas", models.JSONField(default=list, blank=True)),
                ("anomalies", models.JSONField(default=list, blank=True)),
                ("recommendations", models.JSONField(default=list, blank=True)),
                ("model_used", models.CharField(max_length=80, blank=True)),
                ("tokens_used", models.IntegerField(default=0)),
                ("generation_seconds", models.FloatField(default=0.0)),
                ("error_message", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(null=True, blank=True)),
                ("sent_to", models.JSONField(default=list, blank=True)),
                ("tenant", models.ForeignKey(to="core.tenant",
                    on_delete=models.CASCADE, related_name="executive_digests")),
            ],
            options={
                "ordering": ("-period_start",),
                "unique_together": {("tenant", "period", "period_start")},
            },
        ),
        migrations.AddIndex(
            model_name="executivedigest",
            index=models.Index(fields=["status", "-period_start"], name="exec_dig_status_ts_idx"),
        ),
    ]
