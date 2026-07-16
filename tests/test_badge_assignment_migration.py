from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
import pytest


@pytest.fixture
def restore_migration_state():
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()
    yield
    MigrationExecutor(connection).migrate(leaf_nodes)


@pytest.mark.django_db(transaction=True)
def test_badge_lifecycle_migration_preserves_legacy_assignments(
    restore_migration_state,
):
    migrate_from = [("devices", "0011_eventtype_deviceevent_eventacknowledgement")]
    migrate_to = [("devices", "0012_badge_lifecycle")]

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    old_apps = executor.loader.project_state(migrate_from).apps

    Tenant = old_apps.get_model("core", "Tenant")
    Badge = old_apps.get_model("devices", "Badge")
    BadgeAssignment = old_apps.get_model("devices", "BadgeAssignment")

    tenant = Tenant.objects.create(name="Migration test", code="migration-test")
    badge = Badge.objects.create(
        tenant=tenant,
        uid="MIGRATION-BADGE-001",
        type="nfc",
        status="active",
        holder_kind="employee",
    )
    released_at = timezone.now()
    released = BadgeAssignment.objects.create(
        badge=badge,
        holder_kind="employee",
        holder_object_id=1,
        holder_label="Ancienne affectation rendue",
        released_at=released_at,
    )
    older_open = BadgeAssignment.objects.create(
        badge=badge,
        holder_kind="employee",
        holder_object_id=2,
        holder_label="Ancienne affectation ouverte",
    )
    latest_open = BadgeAssignment.objects.create(
        badge=badge,
        holder_kind="employee",
        holder_object_id=3,
        holder_label="Affectation active conservée",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(migrate_to)
    new_apps = executor.loader.project_state(migrate_to).apps
    MigratedAssignment = new_apps.get_model("devices", "BadgeAssignment")

    rows = MigratedAssignment.objects.filter(badge_id=badge.pk)
    assert rows.count() == 3
    assert set(rows.values_list("tenant_id", flat=True)) == {tenant.pk}

    migrated_released = rows.get(pk=released.pk)
    assert migrated_released.closed_at == released_at
    assert migrated_released.close_reason == "unassigned"

    migrated_older = rows.get(pk=older_open.pk)
    assert migrated_older.closed_at is not None
    assert migrated_older.close_reason == "replaced"

    migrated_latest = rows.get(pk=latest_open.pk)
    assert migrated_latest.closed_at is None
    assert rows.filter(closed_at__isnull=True).count() == 1
