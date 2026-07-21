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


def add_missing_audit_columns(apps, schema_editor):
    """Ajoute les colonnes d'audit sans échouer sur un schéma déjà corrigé."""
    connection = schema_editor.connection

    for model_name in AUDITED_MODELS:
        model = apps.get_model("devices", model_name)
        table_name = model._meta.db_table
        with connection.cursor() as cursor:
            description = connection.introspection.get_table_description(cursor, table_name)
        existing_columns = {column.name for column in description}

        for field_name in ("created_by", "updated_by"):
            field = model._meta.get_field(field_name)
            if field.column in existing_columns:
                continue
            schema_editor.add_field(model, field)
            existing_columns.add(field.column)


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0016_edgegatewaypackage_go_platforms"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    audit_state_operations = [
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

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=audit_state_operations,
            database_operations=[],
        ),
        migrations.RunPython(add_missing_audit_columns, migrations.RunPython.noop),
    ]
