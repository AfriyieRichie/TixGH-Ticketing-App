"""Badge contents for conference check-in desks."""

from apps.events.models import WRISTBAND_HEX
from apps.orders.models import Ticket


def _vcard_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\,").replace(";", "\;").replace("\n", " ")


def contact_vcard(ticket: Ticket) -> str | None:
    """A contact card any phone camera can save, only if the attendee agreed."""
    if not ticket.share_contact:
        return None
    order = ticket.order
    name = ticket.attendee_name or order.buyer_name
    phone = ticket.attendee_phone or order.buyer_phone
    email = ticket.attendee_email or order.buyer_email
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_vcard_escape(name)}"]
    if ticket.attendee_organization:
        lines.append(f"ORG:{_vcard_escape(ticket.attendee_organization)}")
    if ticket.attendee_job_title:
        lines.append(f"TITLE:{_vcard_escape(ticket.attendee_job_title)}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{phone}")
    if email:
        lines.append(f"EMAIL:{email}")
    lines.append(f"NOTE:Met at {_vcard_escape(ticket.event.title)}")
    lines.append("END:VCARD")
    return "\n".join(lines)


def badge_role(ticket: Ticket) -> str:
    return ticket.badge_role or ticket.ticket_type.badge_role or ticket.ticket_type.name


def wristband(ticket_type) -> dict | None:
    if not ticket_type.wristband_color:
        return None
    return {
        "color": ticket_type.wristband_color,
        "label": ticket_type.get_wristband_color_display(),
        "hex": WRISTBAND_HEX[ticket_type.wristband_color],
    }


def badge_data(ticket: Ticket) -> dict:
    ev = ticket.event
    return {
        "code": ticket.code,
        "name": ticket.attendee_name or ticket.order.buyer_name,
        "organization": ticket.attendee_organization,
        "job_title": ticket.attendee_job_title,
        "role": badge_role(ticket),
        "ticket_type": ticket.ticket_type.name,
        "event_title": ev.title,
        "event_code": ev.badge_event_code,
        "qr": contact_vcard(ticket),
        "share_contact": ticket.share_contact,
        "checked_in_at": ticket.checked_in_at,
        "printed_at": ticket.badge_printed_at,
        "print_count": ticket.badge_print_count,
        "status": ticket.status,
    }
