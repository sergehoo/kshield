"""Migration : ajout du modèle Camera (caméras IP avec streaming)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0002_badgeassignment_badgescanevent_badge_category_and_more"),
        ("sites", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Camera",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),

                ("name", models.CharField(max_length=120,
                    help_text="Nom affiché (ex: Portail Nord)")),
                ("location_label", models.CharField(max_length=120, blank=True,
                    help_text="Description libre de l'emplacement physique (ex: Mât SE, hauteur 4m)")),

                ("rtsp_url", models.CharField(max_length=500,
                    help_text="URL RTSP/HTTP du flux. Ex: rtsp://user:pass@192.168.1.50:554/Streaming/Channels/101")),
                ("transport", models.CharField(max_length=4, default="tcp", choices=[
                    ("tcp", "TCP (fiable)"), ("udp", "UDP (faible latence)"),
                ])),
                ("codec", models.CharField(max_length=8, default="h264", choices=[
                    ("h264", "H.264"), ("h265", "H.265 / HEVC"), ("mjpeg", "MJPEG"),
                ])),
                ("username", models.CharField(max_length=120, blank=True)),
                ("password", models.CharField(max_length=255, blank=True,
                    help_text="À chiffrer en prod (django-cryptography ou pgcrypto).")),

                ("target_width", models.PositiveIntegerField(default=1280)),
                ("target_height", models.PositiveIntegerField(default=720)),
                ("target_fps", models.PositiveIntegerField(default=10,
                    help_text="FPS de re-streaming JPEG côté serveur (5-15 conseillé).")),
                ("jpeg_quality", models.PositiveIntegerField(default=75,
                    help_text="Qualité JPEG 1-100 du re-stream (compromis bande passante/qualité).")),

                ("onvif_enabled", models.BooleanField(default=False)),
                ("onvif_host", models.CharField(max_length=120, blank=True)),
                ("onvif_port", models.PositiveIntegerField(default=80)),

                ("enable_face_recognition", models.BooleanField(default=False,
                    help_text="Exécute InsightFace sur chaque N-ième frame pour identifier les visages.")),
                ("enable_motion_detection", models.BooleanField(default=False)),
                ("enable_recording", models.BooleanField(default=False,
                    help_text="Enregistre les segments vidéo (rolling buffer 24h).")),

                ("status", models.CharField(max_length=10, default="offline", choices=[
                    ("online", "En ligne"), ("offline", "Hors ligne"),
                    ("error", "Erreur"), ("disabled", "Désactivée"),
                ])),
                ("is_active", models.BooleanField(default=True, db_index=True)),
                ("last_seen_at", models.DateTimeField(null=True, blank=True)),
                ("last_error", models.TextField(blank=True)),
                ("last_snapshot", models.ImageField(upload_to="cameras/snapshots/", null=True, blank=True,
                    help_text="Dernière vignette capturée (régénérée toutes les N minutes).")),

                ("site", models.ForeignKey(to="sites.site", on_delete=models.CASCADE,
                    related_name="cameras", null=True, blank=True)),
                ("zone", models.ForeignKey(to="sites.zone", on_delete=models.SET_NULL,
                    related_name="cameras", null=True, blank=True)),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.AddIndex(
            model_name="camera",
            index=models.Index(fields=["site", "status"], name="cam_site_status_idx"),
        ),
        migrations.AddIndex(
            model_name="camera",
            index=models.Index(fields=["is_active"], name="cam_active_idx"),
        ),
    ]
