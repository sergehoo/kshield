"""Migration : Camera.password → EncryptedCharField (Fernet) + max_length=512.

Les valeurs déjà en clair restent lisibles grâce au fallback `from_db_value`
de _EncryptedFieldMixin (passthrough sur InvalidToken). Au prochain save
de chaque caméra, le champ sera re-stocké chiffré automatiquement.

Pour forcer le ré-chiffrement immédiat de toute la base :
    Camera.objects.all().update_or_create(...)  # ou save individuel
"""
from django.db import migrations

from core.fields import EncryptedCharField


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0003_camera"),
    ]

    operations = [
        migrations.AlterField(
            model_name="camera",
            name="password",
            field=EncryptedCharField(
                blank=True, max_length=512,
                help_text=("Chiffré Fernet au repos (cf. core/fields.py). En prod, "
                            "définir FIELD_ENCRYPTION_KEY dans .env."),
            ),
        ),
    ]
