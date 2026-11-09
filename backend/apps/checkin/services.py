"""
Gate check-in.

The server is the source of truth: a ticket can be admitted once. Each check-in
locks the ticket row, so two gates scanning the same QR at the same moment
can't both admit it. Phones that scanned offline upload their scans later
(`sync_scans`); if another gate already admitted that ticket, the later scan
is reported back as a duplicate.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.events.models import EventStatus
from apps.orders.models import Ticket, TicketStatus
from apps.tickets.models import TicketTransfer
from apps.tickets.signing import PREFIX, parse_payload

from .models import CheckIn, ScanResult

MESSAGES = {
    ScanResult.OK: "Admit",
    ScanResult.DUPLICATE: "Already checked in",
    ScanResult.INVALID: "Not a valid ticket",
    ScanResult.TRANSFERRED: "Old QR: this ticket was transferred to someone else",
    ScanResult.VOID: "Ticket cancelled or refunded",
    ScanResult.WRONG_EVENT: "Ticket is for a different event",
    ScanResult.EVENT_CANCELLED: "This event was cancelled",
}

UNDO_WINDOW = timedelta(minutes=10)


def ticket_row(t: Ticket) -> dict:
    """Compact ticket record for scanner devices."""
    return {
        "id": t.pk,
        "code": t.code,
        "type": t.ticket_type.name,
        "admits": t.ticket_type.admits,
        "name": t.attendee_name or t.order.buyer_name,
        "status": t.status,
        "checked_in_at": t.checked_in_at,
    }


def event_stats(event) -> dict:
    agg = Ticket.objects.filter(event=event).exclude(status=TicketStatus.VOID).aggregate(
        tickets=Count("id"),
        checked_in=Count("id", filter=Q(status=TicketStatus.CHECKED_IN)),
        people=Sum("ticket_type__admits"),
        people_in=Sum("ticket_type__admits", filter=Q(status=TicketStatus.CHECKED_IN)),
    )
    return {k: v or 0 for k, v in agg.items()}


def _clamp(scanned_at):
    now = timezone.now()
    if scanned_at is None or scanned_at > now:
        return now
    return scanned_at


def check_in(event, raw: str, *, user, gate: str = "", device_id: str = "", scanned_at=None) -> dict:
    raw = (raw or "").strip()[:120]
    scanned_at = _clamp(scanned_at)
    code = parse_payload(raw, event.pk)
    ticket = None
    previous = None

    with transaction.atomic():
        if code is None:
            # A well-formed QR whose signature doesn't match: forged, or another event's ticket.
            other = raw.split(":")[1] if raw.startswith(f"{PREFIX}:") and raw.count(":") == 2 else None
            other_ticket = Ticket.objects.filter(code=other).only("event_id").first() if other else None
            result = ScanResult.WRONG_EVENT if other_ticket and other_ticket.event_id != event.pk else ScanResult.INVALID
        else:
            ticket = (
                Ticket.objects.select_for_update()
                .select_related("ticket_type", "order")
                .filter(code=code)
                .first()
            )
            if ticket is None:
                transferred = TicketTransfer.objects.filter(old_code=code, ticket__event=event).exists()
                result = ScanResult.TRANSFERRED if transferred else ScanResult.INVALID
            elif ticket.event_id != event.pk:
                result, ticket = ScanResult.WRONG_EVENT, None
            elif event.status == EventStatus.CANCELLED:
                result = ScanResult.EVENT_CANCELLED
            elif ticket.status == TicketStatus.VOID:
                result = ScanResult.VOID
            elif ticket.status == TicketStatus.CHECKED_IN:
                result = ScanResult.DUPLICATE
                previous = (
                    CheckIn.objects.filter(ticket=ticket, result=ScanResult.OK, undone_at__isnull=True)
                    .order_by("scanned_at")
                    .first()
                )
            else:
                result = ScanResult.OK
                ticket.status = TicketStatus.CHECKED_IN
                ticket.checked_in_at = scanned_at
                ticket.save(update_fields=["status", "checked_in_at", "updated_at"])

        CheckIn.objects.create(
            event=event, ticket=ticket, raw=raw, result=result, scanned_by=user,
            gate=gate[:40], device_id=device_id[:64], scanned_at=scanned_at,
        )

    response = {"result": result, "message": MESSAGES[result], "scanned_at": scanned_at, "ticket": None}
    if ticket is not None:
        response["ticket"] = ticket_row(ticket)
    if previous is not None:
        response["previous"] = {"at": previous.scanned_at, "gate": previous.gate}
    return response


def sync_scans(event, scans: list[dict], *, user, device_id: str = "") -> list[dict]:
    """Apply scans recorded offline, oldest first. Returns one result per scan (same order)."""
    order = sorted(range(len(scans)), key=lambda i: scans[i].get("scanned_at") or timezone.now())
    results: list[dict | None] = [None] * len(scans)
    for i in order:
        s = scans[i]
        results[i] = {
            "client_id": s.get("client_id"),
            **check_in(event, s["raw"], user=user, gate=s.get("gate", ""), device_id=device_id,
                       scanned_at=s.get("scanned_at")),
        }
    return results  # type: ignore[return-value]


class UndoError(Exception):
    pass


def undo_check_in(event, code: str, *, user, can_manage: bool) -> Ticket:
    """Reverse an admission made by mistake (own scans within 10 minutes, or any by an event manager)."""
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().filter(event=event, code=code.strip().upper()).first()
        if ticket is None or ticket.status != TicketStatus.CHECKED_IN:
            raise UndoError("This ticket isn't checked in.")
        scan = CheckIn.objects.filter(ticket=ticket, result=ScanResult.OK, undone_at__isnull=True).order_by("-scanned_at").first()
        if not can_manage:
            if scan is None or scan.scanned_by_id != user.id or timezone.now() - scan.received_at > UNDO_WINDOW:
                raise UndoError("Only an event manager can undo this check-in.")
        if scan:
            scan.undone_at = timezone.now()
            scan.save(update_fields=["undone_at"])
        ticket.status = TicketStatus.VALID
        ticket.checked_in_at = None
        ticket.save(update_fields=["status", "checked_in_at", "updated_at"])
    return ticket
