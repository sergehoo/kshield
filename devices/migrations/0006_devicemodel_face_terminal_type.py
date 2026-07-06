"""Ajoute le type `face_terminal` aux choix DeviceModel.type."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0005_merge_20260512_0953"),
    ]

    operations = [
        migrations.AlterField(
            model_name="devicemodel",
            name="type",
            field=models.CharField(
                choices=[
                    ("reader_uhf_fixed", "Lecteur UHF fixe"),
                    ("reader_uhf_mobile", "Lecteur UHF mobile"),
                    ("reader_nfc_fixed", "Lecteur NFC fixe"),
                    ("reader_nfc_mobile", "Lecteur NFC mobile"),
                    ("tag_uhf", "Tag RFID UHF"),
                    ("beacon_ble", "Beacon BLE"),
                    ("tablet", "Tablette"),
                    ("smartphone", "Smartphone"),
                    ("id_scanner", "Scanner pièce d'identité"),
                    ("door_lock", "Gâche électrique"),
                    ("camera", "Caméra"),
                    ("portique", "Portique RFID"),
                    ("face_terminal", "Terminal reconnaissance faciale"),
                ],
                max_length=24,
            ),
        ),
    ]
