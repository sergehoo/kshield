"""Migration : FaceSightingEvent + FaceCheckinConfirmation (présence par face)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0002_initial"),
        ("devices", "0003_camera"),
        ("employees", "0002_employee_work_location_faceprofile"),
        ("sites", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FaceSightingEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("timestamp", models.DateTimeField(db_index=True)),
                ("face_score", models.FloatField(default=0.0, help_text="Similarité cosine 0-1")),
                ("liveness_score", models.FloatField(null=True, blank=True,
                    help_text="Score anti-spoof real_score 0-1 (null si liveness off)")),
                ("bbox", models.JSONField(default=list, blank=True,
                    help_text="[x1, y1, x2, y2] dans le repère image")),
                ("snapshot", models.ImageField(upload_to="face_sightings/%Y/%m/%d/",
                    null=True, blank=True,
                    help_text="Crop ou frame complète au moment du sighting")),
                ("matched", models.BooleanField(default=False, db_index=True)),
                ("camera", models.ForeignKey(to="devices.camera",
                    on_delete=models.CASCADE, related_name="sightings")),
                ("site", models.ForeignKey(to="sites.site",
                    on_delete=models.SET_NULL,
                    related_name="face_sightings", null=True, blank=True)),
                ("employee", models.ForeignKey(to="employees.employee",
                    on_delete=models.SET_NULL,
                    related_name="face_sightings", null=True, blank=True,
                    db_index=True)),
            ],
            options={"ordering": ("-timestamp",)},
        ),
        migrations.AddIndex(
            model_name="facesightingevent",
            index=models.Index(fields=["employee", "timestamp"],
                                name="sight_emp_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="facesightingevent",
            index=models.Index(fields=["camera", "timestamp"],
                                name="sight_cam_ts_idx"),
        ),
        migrations.AddIndex(
            model_name="facesightingevent",
            index=models.Index(fields=["matched", "timestamp"],
                                name="sight_match_ts_idx"),
        ),

        migrations.CreateModel(
            name="FaceCheckinConfirmation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField(db_index=True)),
                ("kind", models.CharField(max_length=10, choices=[
                    ("arrival", "Arrivée bureau"),
                    ("departure", "Départ bureau"),
                ])),
                ("delta_seconds", models.IntegerField(null=True, blank=True,
                    help_text="Écart temporel face↔badge (positif = badge après face)")),
                ("status", models.CharField(max_length=16, default="confirmed",
                    db_index=True, choices=[
                        ("confirmed", "Confirmé (badge + face matchent)"),
                        ("face_only", "Visage seul (pas de badge)"),
                        ("badge_only", "Badge seul (pas de visage)"),
                        ("out_of_window", "Hors fenêtre temporelle"),
                    ])),
                ("notes", models.TextField(blank=True)),
                ("employee", models.ForeignKey(to="employees.employee",
                    on_delete=models.CASCADE,
                    related_name="checkin_confirmations")),
                ("sighting", models.OneToOneField(to="attendance.facesightingevent",
                    on_delete=models.SET_NULL,
                    related_name="confirmation", null=True, blank=True)),
                ("punch", models.ForeignKey(to="attendance.punch",
                    on_delete=models.SET_NULL,
                    related_name="face_confirmations", null=True, blank=True)),
            ],
            options={
                "ordering": ("-date", "kind"),
                "unique_together": {("employee", "date", "kind")},
            },
        ),
        migrations.AddIndex(
            model_name="facecheckinconfirmation",
            index=models.Index(fields=["date", "kind"], name="conf_date_kind_idx"),
        ),
        migrations.AddIndex(
            model_name="facecheckinconfirmation",
            index=models.Index(fields=["status"], name="conf_status_idx"),
        ),
    ]
