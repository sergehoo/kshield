"""Ajoute 5 plateformes Go (macOS ARM/Intel, Linux amd64/arm64, Windows amd64)
au choix de EdgeGatewayPackage.platform. Pas de changement de schéma DB —
uniquement une extension des ``choices`` pour la validation admin/serializer.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0015_local_agent_ecosystem"),
    ]

    operations = [
        migrations.AlterField(
            model_name="edgegatewaypackage",
            name="platform",
            field=models.CharField(
                choices=[
                    ("windows_exe",      "Windows (Installateur .exe)"),
                    ("windows_portable", "Windows (Portable ZIP)"),
                    ("linux_deb",        "Linux (.deb)"),
                    ("linux_rpm",        "Linux (.rpm)"),
                    ("linux_sh",         "Linux (script universel)"),
                    ("macos_pkg",        "macOS (.pkg)"),
                    ("docker",           "Docker Compose"),
                    ("raspberry_pi",     "Raspberry Pi"),
                    ("mini_pc",          "Mini PC industriel"),
                    ("darwin_arm64_go",  "macOS Apple Silicon (Go)"),
                    ("darwin_amd64_go",  "macOS Intel (Go)"),
                    ("linux_amd64_go",   "Linux amd64 (Go)"),
                    ("linux_arm64_go",   "Linux arm64 / RPi 4-5 (Go)"),
                    ("windows_amd64_go", "Windows amd64 (Go)"),
                    ("windows",          "Windows (legacy)"),
                ],
                db_index=True,
                max_length=24,
            ),
        ),
    ]
