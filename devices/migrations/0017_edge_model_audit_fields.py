from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


AUDITED_MODELS = (
    "devicediscovery",
    "devicediscoveryscan",
    "edgesyncbatch",
    "edgesyncconflict",
    "eventtype",
    "localagentconfiguration",
    "localagenttype",
)


def _audit_field():
    return models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name="+",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0016_edgegatewaypackage_go_platforms"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        operation
        for model_name in AUDITED_MODELS
        for operation in (
            migrations.AddField(
                model_name=model_name,
                name="created_by",
                field=_audit_field(),
            ),
            migrations.AddField(
                model_name=model_name,
                name="updated_by",
                field=_audit_field(),
            ),
        )
    ]
