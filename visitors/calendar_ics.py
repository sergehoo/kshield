"""KAYDAN SHIELD — Génération iCalendar (RFC 5545) pour les visites."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


def _fmt_dt(dt) -> str:
    """Convertit un datetime en YYYYMMDDTHHMMSSZ (UTC)."""
    if dt.tzinfo is None:
        dt = timezone.make_aware(dt)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _escape(s: str) -> str:
    return (str(s).replace("\\", "\\\\")
                  .replace(",", "\\,")
                  .replace(";", "\\;")
                  .replace("\n", "\\n"))


def visit_to_ics(visit_request) -> str:
    """Construit un fichier .ics pour une VisitRequest.

    Compatible Google Calendar / Outlook / Apple Calendar.
    """
    visitor = visit_request.visitor
    site = visit_request.site
    host = visit_request.host_employee

    start = visit_request.scheduled_at or timezone.now()
    duration = timedelta(minutes=visit_request.expected_duration_minutes or 60)
    end = start + duration

    summary = f"Visite KAYDAN — {visitor.first_name} {visitor.last_name}"
    if host:
        summary += f" (hôte : {host.first_name} {host.last_name})"

    location = ""
    if site:
        location = site.name
        if getattr(site, "address", ""):
            location += f" — {site.address}"

    description = (
        f"Visiteur : {visitor.first_name} {visitor.last_name}\\n"
        f"Société : {visitor.company or '—'}\\n"
        f"Hôte : {host.first_name + ' ' + host.last_name if host else '—'}\\n"
        f"Site : {site.name if site else '—'}\\n"
        f"Référence : VR{visit_request.id}\\n\\n"
        f"Présentez-vous à l'accueil avec votre pièce d'identité."
    )

    uid = f"vr-{visit_request.id}@kaydangroupe.com"
    now_stamp = _fmt_dt(timezone.now())

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//KAYDAN SHIELD//Visit//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_stamp}",
        f"DTSTART:{_fmt_dt(start)}",
        f"DTEND:{_fmt_dt(end)}",
        f"SUMMARY:{_escape(summary)}",
        f"LOCATION:{_escape(location)}",
        f"DESCRIPTION:{_escape(description)}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ]

    if visitor.email:
        lines.append(f"ATTENDEE;CN={_escape(visitor.first_name + ' ' + visitor.last_name)};"
                     f"RSVP=TRUE:mailto:{visitor.email}")
    if host and getattr(host, "email", ""):
        lines.append(f"ORGANIZER;CN={_escape(host.first_name + ' ' + host.last_name)}:"
                     f"mailto:{host.email}")
    else:
        lines.append("ORGANIZER;CN=KAYDAN GROUPE:mailto:no-reply@kaydangroupe.com")

    lines.extend([
        "BEGIN:VALARM",
        "TRIGGER:-PT30M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_escape(summary)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ])
    return "\r\n".join(lines) + "\r\n"
