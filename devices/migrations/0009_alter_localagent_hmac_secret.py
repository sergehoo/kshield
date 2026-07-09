"""Elargit LocalAgent.hmac_secret de 128 → 512 caractères.

Le champ est EncryptedCharField (chiffrement Fernet). Un secret brut de
43 chars devient ~130-180 chars une fois chiffré → dépassait max_length=128.
"""
from django.db import migrations

import core.fields


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0008_localagent_activated_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="localagent",
            name="hmac_secret",
            field=core.fields.EncryptedCharField(
                blank=True, max_length=512,
                help_text="Secret HMAC pour signer les messages (stocké chiffré).",
            ),
        ),
    ]
