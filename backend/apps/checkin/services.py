"""
Gate check-in.

The server is the source of truth. Each scan locks the ticket row, so two
gates can't let the same ticket in at the same moment. Phones that scanned
offline upload their scans later (`sync_scans`) and get the server's verdict.

Ticket gate state (a ticket may admit several people, e.g. a table for 8):
    admitted   people who have entered at least once (<= admits)
    inside     people currently inside (<= admitted)
    reentries  times people on this ticket came back in after leaving

Entry:  first-timers are always allowed (up to `admits`). People coming back
        need the event's re-entry policy (allowed, before cut-off, under limit).
Exit:   only meaningful when someone is inside; frees the ticket so its holder
        can come back. While the holder is inside, the same QR shows
        "already inside", so a screenshot sent to a friend outside is useless.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.events.models import EventStatus
from apps.orders.models import Ticket, TicketStatus
from apps.tickets.models import TicketTransfer
from apps.tickets.signing import PREFIX, parse_payload

from .models import CheckIn, Direction, ScanResult

MESSAGES = {
    ScanResult.OK: "Admit",
    ScanResult.REENTRY: "Welcome back",
    ScanResult.EXIT: "Exit recorded",
    ScanResult.DUPLICATE: "Already inside",
    ScanResult.NO_REENTRY: "Re-entry not allowed",
    ScanResult.NOT_INSIDE: "This ticket isn't inside",
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
        "admitted": t.admitted,
        "inside": t.inside,
        "reentries": t.reentries,
    }


def reentry_policy(event) -> dict:
    return {
        "reentry_allowed": event.reentry_allowed,
        "max_reentries": event.max_reentries,
        "reentry_cutoff_at": event.reentry_cutoff_at,
    }


def event_stats(event) -> dict:
    agg = Ticket.objects.filter(event=event).exclude(status=TicketStatus.VOID).aggregate(
        tickets=Count("id"),
        checked_in=Count("id", filter=Q(admitted__gt=0)),
        people=Sum("ticket_type__admits"),
        people_arrived=Sum("admitted"),
        people_in=Sum("inside"),
    )
    return {k: v or 0 for k, v in agg.items()}


def _clamp(scanned_at):
    now = timezone.now()
    if scanned_at is None or scanned_at > now:
        return now
    return scanned_at


def _reentry_problem(event, ticket, at) -> str | None:
    if not event.reentry_allowed:
        return "No re-entry for this event"
    if event.reentry_cutoff_at and at >= event.reentry_cutoff_at:
        return f"Re-entry closed at {timezone.localtime(event.reentry_cutoff_at):%H:%M}"
    if event.max_reentries is not None and ticket.reentries >= event.max_reentries:
        return f"Re-entry limit reached ({event.max_reentries})"
    return None


def _last_entry(ticket):
    return (
        CheckIn.objects.filter(ticket=ticket, result__in=[ScanResult.OK, ScanResult.REENTRY], undone_at__isnull=True)
        .order_by("-scanned_at")
        .first()
    )


def _enter(event, ticket, count, at) -> tuple[str, str, dict]:
    """Returns (result, message, deltas) and updates `ticket` in memory."""
    admits = ticket.ticket_type.admits
    never_in = admits - ticket.admitted
    returning = ticket.admitted - ticket.inside
    if never_in + returning == 0:
        msg = "Already inside" if admits == 1 else f"All {admits} already inside"
        return ScanResult.DUPLICATE, msg, {}

    # Default: everyone on the ticket who hasn't arrived yet; otherwise the people coming back.
    want = min(count or (never_in or returning), never_in + returning)
    new = min(want, never_in)
    back = want - new
    note = ""
    if back:
        problem = _reentry_problem(event, ticket, at)
        if problem:
            if not new:
                return ScanResult.NO_REENTRY, problem, {}
            back, note = 0, f" ({problem.lower()} for the others)"

    ticket.admitted += new
    ticket.inside += new + back
    if back:
        ticket.reentries += 1
    if ticket.status != TicketStatus.CHECKED_IN:
        ticket.status = TicketStatus.CHECKED_IN
        ticket.checked_in_at = at
    result = ScanResult.REENTRY if back and not new else ScanResult.OK
    people = new + back
    msg = MESSAGES[result] if admits == 1 else f"{MESSAGES[result]}: {people} of {admits}{note}"
    return result, msg, {"admitted": new, "inside": new + back, "reentries": 1 if back else 0}


def _exit(event, ticket, count) -> tuple[str, str, dict]:
    if ticket.inside == 0:
        return ScanResult.NOT_INSIDE, "This ticket isn't inside", {}
    n = min(count or ticket.inside, ticket.inside)
    ticket.inside -= n
    admits = ticket.ticket_type.admits
    msg = "Exit recorded" if admits == 1 else f"Exit: {n} of {admits}"
    if not event.reentry_allowed:
        msg += ". No re-entry for this event"
    return ScanResult.EXIT, msg, {"inside": -n}


def check_in(event, raw: str, *, user, gate: str = "", device_id: str = "", scanned_at=None,
             direction: str = Direction.IN, count: int | None = None) -> dict:
    raw = (raw or "").strip()[:120]
    scanned_at = _clamp(scanned_at)
    code = parse_payload(raw, event.pk)
    ticket = None
    previous = None
    deltas: dict = {}
    message = None

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
            else:
                if direction == Direction.OUT:
                    result, message, deltas = _exit(event, ticket, count)
                else:
                    result, message, deltas = _enter(event, ticket, count, scanned_at)
                    if result in (ScanResult.DUPLICATE, ScanResult.NO_REENTRY):
                        previous = _last_entry(ticket)
                if deltas:
                    ticket.save(update_fields=["status", "checked_in_at", "admitted", "inside", "reentries", "updated_at"])

        CheckIn.objects.create(
            event=event, ticket=ticket, raw=raw, result=result, direction=direction,
            people=abs(deltas.get("inside", 0)), delta_admitted=deltas.get("admitted", 0),
            delta_inside=deltas.get("inside", 0), delta_reentries=deltas.get("reentries", 0),
            scanned_by=user, gate=gate[:40], device_id=device_id[:64], scanned_at=scanned_at,
        )

    response = {
        "result": result, "message": message or MESSAGES[result], "direction": direction,
        "people": abs(deltas.get("inside", 0)), "scanned_at": scanned_at, "ticket": None,
    }
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
                       scanned_at=s.get("scanned_at"), direction=s.get("direction", Direction.IN),
                       count=s.get("count")),
        }
    return results  # type: ignore[return-value]


class UndoError(Exception):
    pass


def undo_check_in(event, code: str, *, user, can_manage: bool) -> Ticket:
    """
    Reverse the most recent gate action on a ticket (an entry or an exit made by
    mistake). Scanners can undo their own scans within 10 minutes; event
    managers can undo any.
    """
    with transaction.atomic():
        ticket = (
            Ticket.objects.select_for_update().select_related("ticket_type", "order")
            .filter(event=event, code=code.strip().upper()).first()
        )
        if ticket is None:
            raise UndoError("Ticket not found.")
        scan = (
            CheckIn.objects.filter(ticket=ticket, undone_at__isnull=True)
            .filter(Q(delta_inside__lt=0) | Q(delta_inside__gt=0))
            .order_by("-scanned_at", "-id").first()
        )
        if scan is None:
            raise UndoError("Nothing to undo for this ticket.")
        if not can_manage and (scan.scanned_by_id != user.id or timezone.now() - scan.received_at > UNDO_WINDOW):
            raise UndoError("Only an event manager can undo this scan.")
        ticket.admitted = max(ticket.admitted - scan.delta_admitted, 0)
        ticket.inside = min(max(ticket.inside - scan.delta_inside, 0), ticket.admitted)
        ticket.reentries = max(ticket.reentries - scan.delta_reentries, 0)
        if ticket.admitted == 0:
            ticket.status = TicketStatus.VALID
            ticket.checked_in_at = None
        ticket.save(update_fields=["status", "checked_in_at", "admitted", "inside", "reentries", "updated_at"])
        scan.undone_at = timezone.now()
        scan.save(update_fields=["undone_at"])
    return ticket
