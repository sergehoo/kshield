"""Tests BLE Stillness — agrégation pings + détection casque immobile."""
from datetime import timedelta

import pytest
from django.utils import timezone


@pytest.fixture
def helmet(db, kaydan_tenant):
    from devices.models import Helmet
    return Helmet.objects.create(
        tenant=kaydan_tenant, serial_number="HLM-BLE",
        uhf_tag_uid="UHF-BLE", ble_beacon_uid="BLE-BLE",
        status="active",
    )


def _make_pings(helmet, count, immobile=True, start_offset_min=0):
    """Crée `count` pings espacés de 1s, marquant immobile=True/False."""
    from attendance.models import BLEPresencePing
    base = timezone.now() - timedelta(minutes=start_offset_min)
    pings = []
    for i in range(count):
        pings.append(BLEPresencePing.objects.create(
            helmet=helmet, timestamp=base - timedelta(seconds=i),
            rssi=-50, is_immobile=immobile,
        ))
    return pings


@pytest.mark.integration
def test_roll_up_aggregates_pings(db, helmet):
    from attendance.ble_stillness import roll_up_windows
    from attendance.models import BLEPresenceWindow
    _make_pings(helmet, 60, immobile=True, start_offset_min=2)
    created = roll_up_windows(window_minutes=5)
    assert created >= 1
    w = BLEPresenceWindow.objects.filter(helmet=helmet).first()
    assert w is not None
    assert w.pings_count >= 60
    assert w.immobile_minutes >= 4


@pytest.mark.integration
def test_evaluate_stillness_creates_signal_when_threshold_exceeded(
    db, helmet, settings,
):
    """Avec un casque immobile sur > 30 min, BLEStillnessSignal doit être levé."""
    from antifraud.models import BLEStillnessSignal
    from attendance.ble_stillness import evaluate_stillness
    from attendance.models import BLEPresenceWindow

    # Crée 8 fenêtres de 5 min chacune toutes immobiles → 40 min immobile
    now = timezone.now()
    for i in range(8):
        start = now - timedelta(minutes=5 * (i + 1))
        BLEPresenceWindow.objects.create(
            helmet=helmet, zone=None,
            started_at=start, ended_at=start + timedelta(minutes=5),
            pings_count=300, immobile_minutes=5,
        )
    signals = evaluate_stillness()
    assert len(signals) == 1
    assert signals[0].immobile_minutes >= 30
    assert BLEStillnessSignal.objects.filter(helmet=helmet).count() == 1


@pytest.mark.integration
def test_evaluate_stillness_silent_below_threshold(db, helmet):
    """Un casque immobile 10 min < 30 min ne doit pas lever de signal."""
    from antifraud.models import BLEStillnessSignal
    from attendance.ble_stillness import evaluate_stillness
    from attendance.models import BLEPresenceWindow

    now = timezone.now()
    for i in range(2):  # 2 fenêtres × 5 min = 10 min
        start = now - timedelta(minutes=5 * (i + 1))
        BLEPresenceWindow.objects.create(
            helmet=helmet, zone=None,
            started_at=start, ended_at=start + timedelta(minutes=5),
            pings_count=300, immobile_minutes=5,
        )
    evaluate_stillness()
    assert BLEStillnessSignal.objects.filter(helmet=helmet).count() == 0


@pytest.mark.integration
def test_clear_stillness_marks_signals_resolved(db, helmet):
    from antifraud.models import BLEStillnessSignal
    from attendance.ble_stillness import clear_stillness
    sig = BLEStillnessSignal.objects.create(
        helmet=helmet, zone=None,
        detected_at=timezone.now(), immobile_minutes=35,
    )
    assert sig.cleared_at is None
    clear_stillness(helmet.id)
    sig.refresh_from_db()
    assert sig.cleared_at is not None


@pytest.mark.integration
def test_evaluate_idempotent_when_signal_already_open(db, helmet):
    """Si un BLEStillnessSignal est déjà ouvert, ne pas en créer un autre."""
    from antifraud.models import BLEStillnessSignal
    from attendance.ble_stillness import evaluate_stillness
    from attendance.models import BLEPresenceWindow

    BLEStillnessSignal.objects.create(
        helmet=helmet, zone=None,
        detected_at=timezone.now() - timedelta(minutes=2),
        immobile_minutes=30,
    )
    now = timezone.now()
    for i in range(8):
        start = now - timedelta(minutes=5 * (i + 1))
        BLEPresenceWindow.objects.create(
            helmet=helmet, zone=None,
            started_at=start, ended_at=start + timedelta(minutes=5),
            pings_count=300, immobile_minutes=5,
        )
    evaluate_stillness()
    assert BLEStillnessSignal.objects.filter(helmet=helmet).count() == 1


@pytest.mark.integration
def test_celery_task_returns_summary(db, helmet):
    from attendance.tasks import ble_rollup_and_evaluate
    result = ble_rollup_and_evaluate()
    assert "windows_created" in result
    assert "signals_created" in result
