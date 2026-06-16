"""KAYDAN SHIELD — tâches Celery pour la synchronisation des terminaux ZKTeco.

Deux jobs périodiques :

- ``sync_zkteco_attendances``  : récupère les pointages depuis chaque terminal
  ZKTeco actif et crée les ``AccessEvent`` correspondants côté Shield.
- ``push_zkteco_users`` : pousse vers chaque terminal les utilisateurs
  autorisés (employés + ouvriers actifs avec carte assignée).

Chaque job est idempotent et best-effort : si un terminal est offline, on
log un warning et on continue avec les suivants.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


def _zkteco_devices_qs():
    """Renvoie le queryset des terminaux ZKTeco actifs.

    Note : on ne fait PAS `exclude(ip_address__exact="")` car GenericIPAddressField
    convertit "" en NULL dans le SQL → l'exclude se transforme en condition
    pathologique sur SQLite et vide le queryset. Le `isnull=False` suffit.
    """
    from django.db.models import Q

    from .models import Device
    return (
        Device.objects
        .select_related("model", "site")
        .filter(status="active", ip_address__isnull=False)
        .filter(
            Q(model__brand__icontains="zkteco")
            | Q(model__brand__icontains="anviz")
            | Q(model__brand__icontains="biopointer")
            | Q(model__brand__iexact="zk")
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sync attendances : PULL des pointages
# ─────────────────────────────────────────────────────────────────────────────
@shared_task(name="devices.sync_zkteco_attendances",
             autoretry_for=(Exception,),
             retry_kwargs={"max_retries": 2, "countdown": 60})
def sync_zkteco_attendances(device_id: Optional[int] = None) -> dict:
    """Pull les pointages de chaque terminal ZKTeco actif.

    Args:
        device_id: si fourni, ne sync QUE ce terminal. Sinon tous.

    Returns:
        {"synced_devices": N, "events_created": M, "errors": [...]}
    """
    from access_control.models import AccessEvent

    from .zk_client import ZkConnectionError, ZkUnavailable, safe_zk_session

    qs = _zkteco_devices_qs()
    if device_id:
        qs = qs.filter(pk=device_id)

    synced = 0
    events_created = 0
    errors = []

    for device in qs:
        # last_heartbeat_at sert aussi de "watermark" pour éviter les doublons.
        # On préfère un cache dédié si dispo.
        from django.core.cache import cache
        cache_key = f"zk_last_sync:{device.pk}"
        since_iso = cache.get(cache_key)
        since = None
        if since_iso:
            try:
                since = datetime.fromisoformat(since_iso)
            except Exception:
                since = None
        if not since:
            # Premier sync : on prend les pointages des dernières 24h pour limiter
            since = (timezone.now() - timedelta(hours=24)).replace(tzinfo=None)

        with safe_zk_session(
            ip=device.ip_address, port=4370,
            password=int((device.model.spec or {}).get("sdk_password", 0))
            if device.model and isinstance(device.model.spec, dict) else 0,
        ) as zk:
            if zk is None:
                errors.append({"device_id": device.pk, "error": "session impossible"})
                continue

            try:
                attendances = zk.pull_attendances(since=since)
            except ZkConnectionError as exc:
                errors.append({"device_id": device.pk, "error": str(exc)})
                continue

            # Heartbeat OK
            device.last_heartbeat_at = timezone.now()
            device.save(update_fields=["last_heartbeat_at"])

            for att in attendances:
                # ZKTeco user_id (str), timestamp (naive), status, punch
                ts = att.timestamp
                if ts.tzinfo is None:
                    ts = timezone.make_aware(ts, timezone.get_current_timezone())

                # Cache du mapping user_id → card pendant la durée du sync.
                from .models import Badge
                if "user_to_card" not in locals():
                    user_to_card = {}
                    try:
                        for u in zk.list_users():
                            card = int(getattr(u, "card", 0) or 0)
                            if card:
                                user_to_card[str(u.user_id)] = card
                    except Exception:
                        pass
                card = user_to_card.get(str(att.user_id))
                badge_uid_str = str(card) if card else str(att.user_id)

                # MULTI-TENANT STRICT : on cherche le badge EXCLUSIVEMENT dans
                # le tenant du device. Évite qu'un K14 d'un tenant A reconnaisse
                # un badge clandestin d'un tenant B sur le même réseau.
                badge = Badge.objects.filter(
                    tenant=device.tenant, uid=badge_uid_str,
                ).first()

                # Détermine le holder (Employee/Worker) si badge attribué
                holder_kind = "unknown"
                holder_ct = None
                holder_oid = None
                if badge and badge.holder_object_id:
                    holder_kind = badge.holder_kind or "unknown"
                    holder_ct = badge.holder_content_type
                    holder_oid = badge.holder_object_id

                # DIRECTION : priorité au checkpoint du device s'il a un type
                # déterministe (entry → in, exit → out). Sinon on alterne via
                # le dernier event de la personne (toggle in/out). Sinon
                # fallback sur le punch K14.
                direction = _resolve_direction(
                    device=device, badge=badge, att=att,
                )

                # Décision : si badge inconnu (pas dans le tenant) → DENIED.
                # Sinon GRANTED (le K14 a déjà validé localement).
                decision = "granted" if badge else "denied"
                denial_reason = "" if badge else f"Badge inconnu : {badge_uid_str}"

                try:
                    AccessEvent.objects.create(
                        tenant=device.tenant,
                        timestamp=ts,
                        site=device.site or _fallback_site(device),
                        zone=getattr(device, "zone", None),
                        checkpoint=getattr(device, "checkpoint", None),
                        direction=direction,
                        method="nfc",
                        decision=decision,
                        denial_reason=denial_reason,
                        device=device,
                        badge_uid=badge_uid_str,
                        holder_kind=holder_kind,
                        holder_content_type=holder_ct,
                        holder_object_id=holder_oid,
                        raw_payload={
                            "source": "zkteco_pull",
                            "zk_user_id": str(att.user_id),
                            "zk_card": card,
                            "zk_punch": getattr(att, "punch", None),
                            "zk_status": getattr(att, "status", None),
                        },
                    )
                    events_created += 1
                except Exception as exc:
                    errors.append({
                        "device_id": device.pk,
                        "ts": ts.isoformat(),
                        "user_id": str(att.user_id),
                        "error": str(exc)[:200],
                    })

            # Watermark : on garde le timestamp du dernier event ingéré.
            if attendances:
                last_ts = max(a.timestamp for a in attendances)
                cache.set(cache_key, last_ts.isoformat(), 7 * 86400)
            synced += 1

    return {
        "synced_devices": synced,
        "events_created": events_created,
        "errors": errors,
    }


def _fallback_site(device):
    """Si le device n'a pas de site, prend le premier site du tenant."""
    from sites.models import Site
    return Site.objects.filter(tenant=device.tenant).first()


def _resolve_direction(device, badge, att):
    """Détermine la direction (in/out) en cascade :

    1. Si le checkpoint du device a un type déterministe → respect strict
    2. Si bidirectional / aucun checkpoint → on TOGGLE depuis le dernier
       event de la personne (in si dernier=out, out si dernier=in)
    3. Sinon fallback sur le `punch` K14 (0=in, 1=out)
    """
    # 1) Checkpoint déterministe
    cp = getattr(device, "checkpoint", None)
    if cp is not None:
        ctype = (getattr(cp, "type", "") or "").lower()
        if ctype == "entry":
            return "in"
        if ctype == "exit":
            return "out"
        # bidirectional / inopine / internal → on continue en cascade

    # 2) Toggle depuis le dernier event de la personne (si badge connu)
    if badge and badge.holder_object_id:
        from access_control.models import AccessEvent
        last = (AccessEvent.objects
                .filter(
                    tenant=device.tenant,
                    holder_kind=badge.holder_kind,
                    holder_object_id=badge.holder_object_id,
                    direction__in=("in", "out"),
                )
                .order_by("-timestamp")
                .only("direction")
                .first())
        if last:
            return "out" if last.direction == "in" else "in"
        # Première fois qu'on voit cette personne → "in" (logique)
        return "in"

    # 3) Fallback punch K14 (0=in, 1=out, autres=pass)
    punch = int(getattr(att, "punch", 0) or 0)
    if punch == 0:
        return "in"
    if punch == 1:
        return "out"
    return "pass"


# ─────────────────────────────────────────────────────────────────────────────
# Push users : envoie les utilisateurs autorisés vers chaque terminal
# ─────────────────────────────────────────────────────────────────────────────
@shared_task(name="devices.push_zkteco_users")
def push_zkteco_users(device_id: Optional[int] = None) -> dict:
    """Pousse vers chaque terminal ZKTeco la liste des badges actifs assignés.

    Pour chaque ``Badge`` actif lié à un Employee ou Worker, on crée/met à jour
    l'utilisateur côté terminal avec ``uid=hash(badge.uid)``, ``card=int(badge.uid)``,
    ``name=holder.full_name``.

    Args:
        device_id: si fourni, push uniquement vers ce terminal.
    """
    from .models import Badge
    from .zk_client import ZkConnectionError, safe_zk_session

    qs = _zkteco_devices_qs()
    if device_id:
        qs = qs.filter(pk=device_id)

    pushed_total = 0
    errors = []

    for device in qs:
        # Badges actifs assignés à un porteur, type NFC/UHF
        badges = (Badge.objects.filter(
            tenant=device.tenant, status="active",
            holder_object_id__isnull=False,
        ).exclude(uid="")[:1000])  # cap soft sur le terminal

        with safe_zk_session(
            ip=device.ip_address, port=4370,
            password=int((device.model.spec or {}).get("sdk_password", 0))
            if device.model and isinstance(device.model.spec, dict) else 0,
        ) as zk:
            if zk is None:
                errors.append({"device_id": device.pk, "error": "session impossible"})
                continue

            pushed = 0
            for b in badges:
                # UID ZKTeco : entier 1..65535. On dérive d'un hash stable du UID badge.
                try:
                    uid_int = int(b.uid, 16) % 65500 + 1 if b.uid.isalnum() else hash(b.uid) % 65500 + 1
                except Exception:
                    uid_int = hash(b.uid) % 65500 + 1
                # Card number ZKTeco : entier décimal du UID hex
                try:
                    card_int = int(b.uid, 16) if not b.uid.isdigit() else int(b.uid)
                except Exception:
                    card_int = 0

                name = ""
                holder = b.holder
                if holder is not None:
                    name = (
                        getattr(holder, "get_full_name", lambda: "")()
                        or f"{getattr(holder, 'first_name', '')} {getattr(holder, 'last_name', '')}"
                    ).strip() or b.uid

                try:
                    zk.set_user(
                        uid=uid_int, name=name[:24], card=card_int,
                        user_id=str(b.uid)[:9],
                    )
                    pushed += 1
                except ZkConnectionError as exc:
                    errors.append({
                        "device_id": device.pk, "badge_uid": b.uid,
                        "error": str(exc)[:200],
                    })

            pushed_total += pushed
            logger.info(
                "ZK push users : device=%s, pushed=%s", device.pk, pushed,
            )

    return {"pushed_users": pushed_total, "errors": errors}
