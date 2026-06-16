"""Tests d'intégration ZKTeco — mock pyzk → AccessEvent → Punch.

Ne nécessite PAS de terminal physique : tous les appels pyzk sont mockés.
Couvre :
  - sync_zkteco_attendances : pull pointages → AccessEvent created
  - push_zkteco_users : badge actif → set_user appelé sur le terminal
  - mapping user_id → card via list_users
  - decision="denied" si badge inconnu
  - direction auto via checkpoint (entry/exit)
  - aggregate_punches : AccessEvent → Punch → AttendanceDay

Lance avec :
    pytest tests/test_zk_integration.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


@pytest.fixture
def setup_minimal_db(db):
    """Crée le minimum : tenant + site + device ZKTeco + employé + badge."""
    from access_control.models import AccessEvent  # noqa: F401
    from accounts.models import User  # noqa: F401
    from core.models import Tenant
    from devices.models import Badge, Device, DeviceModel
    from employees.models import Employee
    from sites.models import Site

    tenant, _ = Tenant.objects.get_or_create(
        code="test-tenant",
        defaults={"name": "Test Tenant", "is_active": True},
    )
    site, _ = Site.objects.get_or_create(
        tenant=tenant, code="HQ",
        defaults={"name": "Headquarters", "status": "active", "type": "office"},
    )
    model, _ = DeviceModel.objects.get_or_create(
        brand="ZKTeco", model="K14/ID",
        defaults={"type": "reader_nfc_fixed", "is_active": True,
                  "spec": {"protocol": "ZKAccess SDK", "sdk_port": 4370}},
    )
    device, _ = Device.objects.get_or_create(
        tenant=tenant, serial_number="TEST-K14-001",
        defaults={
            "model": model, "site": site, "status": "active",
            "ip_address": "10.0.0.99",
        },
    )
    emp, _ = Employee.objects.get_or_create(
        tenant=tenant, matricule="EMP-TEST-001",
        defaults={"first_name": "Test", "last_name": "User",
                  "email": "test@example.com", "status": "active"},
    )
    emp_ct = ContentType.objects.get_for_model(Employee)
    badge, _ = Badge.objects.get_or_create(
        tenant=tenant, uid="6238480",
        defaults={
            "type": "nfc", "category": "employee_rfid", "status": "active",
            "holder_kind": "employee",
            "holder_content_type": emp_ct,
            "holder_object_id": emp.pk,
        },
    )
    return {
        "tenant": tenant, "site": site, "device": device,
        "employee": emp, "badge": badge,
    }


# ─────────────────────────────────────────────────────────────────────────────
# sync_zkteco_attendances
# ─────────────────────────────────────────────────────────────────────────────
class TestSyncAttendances:
    @patch("devices.zk_client.ZkClient")
    def test_pull_creates_access_event_for_known_badge(
        self, mock_zk_class, setup_minimal_db,
    ):
        """Un pointage du K14 avec un user_id mappé sur un Badge connu →
        AccessEvent decision='granted' avec holder lié."""
        from access_control.models import AccessEvent
        from devices.tasks import sync_zkteco_attendances

        # Mock pyzk
        mock_user = MagicMock(user_id="1", name="Test User", card=6238480)
        mock_att = MagicMock(
            user_id="1",
            timestamp=datetime.now() - timedelta(minutes=5),
            status=0, punch=0,
        )
        mock_instance = MagicMock()
        mock_instance.list_users.return_value = [mock_user]
        mock_instance.pull_attendances.return_value = [mock_att]
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_zk_class.return_value.open.return_value = mock_instance

        # Aussi mocker safe_zk_session pour qu'il retourne mock_instance
        with patch("devices.tasks.safe_zk_session") as mock_session:
            mock_session.return_value.__enter__.return_value = mock_instance
            mock_session.return_value.__exit__.return_value = False
            result = sync_zkteco_attendances(device_id=setup_minimal_db["device"].pk)

        assert result["synced_devices"] >= 1
        events = AccessEvent.objects.filter(
            badge_uid="6238480", decision="granted",
        )
        assert events.exists()
        ev = events.first()
        assert ev.holder_kind == "employee"
        assert ev.holder_object_id == setup_minimal_db["employee"].pk

    @patch("devices.tasks.safe_zk_session")
    def test_pull_unknown_card_yields_denied(
        self, mock_session, setup_minimal_db,
    ):
        """Carte non connue dans le tenant du device → decision='denied'."""
        from access_control.models import AccessEvent
        from devices.tasks import sync_zkteco_attendances

        mock_user = MagicMock(user_id="999", name="Inconnu", card=99999)
        mock_att = MagicMock(
            user_id="999",
            timestamp=datetime.now() - timedelta(minutes=2),
            status=0, punch=0,
        )
        mock_instance = MagicMock()
        mock_instance.list_users.return_value = [mock_user]
        mock_instance.pull_attendances.return_value = [mock_att]
        mock_session.return_value.__enter__.return_value = mock_instance
        mock_session.return_value.__exit__.return_value = False

        sync_zkteco_attendances(device_id=setup_minimal_db["device"].pk)

        events = AccessEvent.objects.filter(badge_uid="99999")
        assert events.exists()
        assert events.first().decision == "denied"
        assert "inconnu" in events.first().denial_reason.lower()


# ─────────────────────────────────────────────────────────────────────────────
# push_zkteco_users
# ─────────────────────────────────────────────────────────────────────────────
class TestPushUsers:
    @patch("devices.tasks.safe_zk_session")
    def test_push_calls_set_user_on_active_badge(
        self, mock_session, setup_minimal_db,
    ):
        from devices.tasks import push_zkteco_users

        mock_instance = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_instance
        mock_session.return_value.__exit__.return_value = False

        result = push_zkteco_users(device_id=setup_minimal_db["device"].pk)

        assert result["pushed_users"] >= 1
        mock_instance.set_user.assert_called()
        args, kwargs = mock_instance.set_user.call_args
        # Le card pushé doit être le UID badge converti
        assert kwargs["card"] == 6238480


# ─────────────────────────────────────────────────────────────────────────────
# aggregate_punches
# ─────────────────────────────────────────────────────────────────────────────
class TestAggregatePunches:
    def test_creates_punch_morning_in_and_evening_out(self, setup_minimal_db):
        """Crée un Punch matin entrée + soir sortie depuis 2 AccessEvent."""
        from access_control.models import AccessEvent
        from attendance.models import AttendanceDay, Punch
        from attendance.tasks import aggregate_punches

        now = timezone.now()
        # Pointage entrée 08:10
        ev1_ts = now.replace(hour=8, minute=10, second=0, microsecond=0)
        AccessEvent.objects.create(
            tenant=setup_minimal_db["tenant"],
            site=setup_minimal_db["site"],
            timestamp=ev1_ts,
            direction="in", method="nfc", decision="granted",
            badge_uid="6238480",
            holder_kind="employee",
            holder_content_type=ContentType.objects.get_for_model(
                setup_minimal_db["employee"].__class__),
            holder_object_id=setup_minimal_db["employee"].pk,
            device=setup_minimal_db["device"],
        )
        # Pointage sortie 18:00
        ev2_ts = now.replace(hour=18, minute=0, second=0, microsecond=0)
        AccessEvent.objects.create(
            tenant=setup_minimal_db["tenant"],
            site=setup_minimal_db["site"],
            timestamp=ev2_ts,
            direction="out", method="nfc", decision="granted",
            badge_uid="6238480",
            holder_kind="employee",
            holder_content_type=ContentType.objects.get_for_model(
                setup_minimal_db["employee"].__class__),
            holder_object_id=setup_minimal_db["employee"].pk,
            device=setup_minimal_db["device"],
        )

        result = aggregate_punches(days_back=1)

        assert result["punches_created"] >= 2
        punches = Punch.objects.filter(
            holder_object_id=setup_minimal_db["employee"].pk,
        ).order_by("timestamp")
        types = [p.type for p in punches]
        assert "morning_in" in types
        assert "evening_out" in types

        # AttendanceDay créé avec status=present (durée > 4h)
        ad = AttendanceDay.objects.filter(
            holder_object_id=setup_minimal_db["employee"].pk,
        ).first()
        assert ad is not None
        assert ad.status == "present"
        # ~9h50 = 590 min
        assert ad.duration_minutes >= 500

    def test_idempotent_no_duplicate_punches(self, setup_minimal_db):
        """Re-lancer aggregate_punches ne doit pas créer de doublons."""
        from access_control.models import AccessEvent
        from attendance.models import Punch
        from attendance.tasks import aggregate_punches

        now = timezone.now()
        AccessEvent.objects.create(
            tenant=setup_minimal_db["tenant"],
            site=setup_minimal_db["site"],
            timestamp=now.replace(hour=8, minute=5),
            direction="in", method="nfc", decision="granted",
            badge_uid="6238480",
            holder_kind="employee",
            holder_content_type=ContentType.objects.get_for_model(
                setup_minimal_db["employee"].__class__),
            holder_object_id=setup_minimal_db["employee"].pk,
            device=setup_minimal_db["device"],
        )
        aggregate_punches(days_back=1)
        count_first = Punch.objects.count()
        aggregate_punches(days_back=1)   # re-run
        count_second = Punch.objects.count()
        assert count_first == count_second


# ─────────────────────────────────────────────────────────────────────────────
# Direction via checkpoint (Lot 3 des features ZK)
# ─────────────────────────────────────────────────────────────────────────────
class TestDirectionResolution:
    def test_checkpoint_entry_forces_in(self, setup_minimal_db):
        """Si le device a un checkpoint type=entry, la direction est 'in'."""
        from devices.tasks import _resolve_direction
        from sites.models import Checkpoint

        cp = Checkpoint.objects.create(
            site=setup_minimal_db["site"],
            code="MAIN-ENTRY",
            name="Entrée principale",
            type="entry",
            mode="fixed",
            method="nfc",
        )
        setup_minimal_db["device"].checkpoint = cp
        setup_minimal_db["device"].save()

        # punch=1 (out) mais checkpoint=entry → doit forcer "in"
        mock_att = MagicMock(punch=1)
        direction = _resolve_direction(
            device=setup_minimal_db["device"],
            badge=setup_minimal_db["badge"],
            att=mock_att,
        )
        assert direction == "in"
