"""KAYDAN SHIELD — Évaluateur BLE Stillness.

Quand un casque connecté reste immobile au-delà du seuil
`KAYDAN_SHIELD["BLE_STILLNESS_THRESHOLD_MIN"]` (par défaut 30 min),
on lève un `BLEStillnessSignal` (et optionnellement une FraudAlert).

Pipeline :
1. les casques poussent des `BLEPresencePing` à haute fréquence (1/s),
   contenant `is_immobile=True/False` selon l'accéléromètre embarqué ;
2. toutes les 5 min, `roll_up_windows()` agrège ces pings en `BLEPresenceWindow`
   avec `immobile_minutes` cumulés ;
3. `evaluate_stillness()` parcourt les casques actifs et lève
   `BLEStillnessSignal` quand la fenêtre courante dépasse le seuil.

Cette implémentation utilise des requêtes Django simples — aucune dépendance
externe, fonctionne sur SQLite ou PostgreSQL.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def _threshold_min() -> int:
    return int(getattr(settings, "KAYDAN_SHIELD", {}).get("BLE_STILLNESS_THRESHOLD_MIN", 30))


def roll_up_windows(window_minutes: int = 5):
    """Agrège les BLEPresencePing en BLEPresenceWindow par tranches de 5 min.

    Pour chaque casque actif sur la dernière fenêtre, crée (ou met à jour)
    une BLEPresenceWindow avec :
      - pings_count       nombre total de pings
      - immobile_minutes  estimation des minutes immobiles (proportionnelle)
    """
    from attendance.models import BLEPresencePing, BLEPresenceWindow
    now = timezone.now()
    started = (now - timedelta(minutes=window_minutes)).replace(second=0, microsecond=0)
    ended = started + timedelta(minutes=window_minutes)

    aggregates = (BLEPresencePing.objects
                  .filter(timestamp__gte=started, timestamp__lt=ended)
                  .values("helmet_id", "zone_id")
                  .annotate(total=Count("id"),
                             immobile_count=Sum("is_immobile")))

    created = 0
    for row in aggregates:
        if not row["total"]:
            continue
        immo_ratio = (row["immobile_count"] or 0) / row["total"]
        immobile_minutes = int(round(immo_ratio * window_minutes))
        BLEPresenceWindow.objects.update_or_create(
            helmet_id=row["helmet_id"], zone_id=row["zone_id"],
            started_at=started,
            defaults={
                "ended_at": ended,
                "pings_count": row["total"],
                "immobile_minutes": immobile_minutes,
            },
        )
        created += 1
    return created


def evaluate_stillness() -> list:
    """Pour chaque casque, somme les minutes immobiles consécutives sur les
    dernières fenêtres et lève un BLEStillnessSignal si on dépasse le seuil.
    Renvoie la liste des signaux créés.
    """
    from antifraud.models import BLEStillnessSignal
    from attendance.models import BLEPresenceWindow

    threshold = _threshold_min()
    cutoff = timezone.now() - timedelta(minutes=threshold + 5)

    # Pour chaque casque, récupérer ses fenêtres récentes
    helmet_ids = (BLEPresenceWindow.objects
                  .filter(started_at__gte=cutoff)
                  .values_list("helmet_id", flat=True).distinct())

    created = []
    for helmet_id in helmet_ids:
        windows = list(BLEPresenceWindow.objects
                       .filter(helmet_id=helmet_id, started_at__gte=cutoff)
                       .order_by("-started_at")[:max(threshold // 5 + 1, 6)])
        if not windows:
            continue

        # Streak immobile consécutif (en partant de la plus récente)
        consecutive_immobile = 0
        latest_zone = windows[0].zone_id
        for w in windows:
            if w.immobile_minutes >= 4:  # 4 sur 5 min => fenêtre considérée immobile
                consecutive_immobile += w.immobile_minutes
            else:
                break

        if consecutive_immobile < threshold:
            continue

        # Vérifier qu'on n'a pas déjà un signal ouvert récent
        if BLEStillnessSignal.objects.filter(
            helmet_id=helmet_id, cleared_at__isnull=True,
            detected_at__gte=cutoff,
        ).exists():
            continue

        sig = BLEStillnessSignal.objects.create(
            helmet_id=helmet_id, zone_id=latest_zone,
            detected_at=timezone.now(),
            immobile_minutes=consecutive_immobile,
        )
        created.append(sig)
        logger.info("BLEStillnessSignal #%s — casque %s immobile %s min",
                    sig.id, helmet_id, consecutive_immobile)
    return created


def clear_stillness(helmet_id: int):
    """À appeler dès qu'un casque redevient mobile : ferme tous les signaux ouverts."""
    from antifraud.models import BLEStillnessSignal
    BLEStillnessSignal.objects.filter(
        helmet_id=helmet_id, cleared_at__isnull=True,
    ).update(cleared_at=timezone.now())
