from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.otp import Contact
from apps.events.models import EventStatus
from apps.notifications.tasks import deliver_transfer_notice
from apps.orders.models import Ticket, TicketStatus, _access_token, _ticket_code

from .models import TicketTransfer

User = get_user_model()


class TransferError(Exception):
    pass


def _new_code() -> str:
    code = _ticket_code()
    while Ticket.objects.filter(code=code).exists():
        code = _ticket_code()
    return code


def transfer_ticket(ticket: Ticket, *, by_user, to: Contact, to_name: str) -> Ticket:
    """
    Send a ticket to someone else. The ticket gets a NEW code and link, so
    the sender's copy (screenshot, PDF, SMS link) stops working.
    """
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().select_related("event").get(pk=ticket.pk)
        ev = ticket.event
        if ticket.holder_id != by_user.id:
            raise TransferError("Only the ticket holder can transfer this ticket.")
        if ticket.status != TicketStatus.VALID:
            raise TransferError("This ticket can't be transferred (it has been used or voided).")
        if not ev.allow_transfers:
            raise TransferError("The organizer has turned off ticket transfers for this event.")
        if ev.status != EventStatus.PUBLISHED or ev.has_ended:
            raise TransferError("This event is no longer open for transfers.")
        if to.value in (by_user.email, by_user.phone):
            raise TransferError("You already hold this ticket.")

        field = "email" if to.is_email else "phone"
        recipient = User.objects.filter(**{field: to.value}, is_active=True).first()
        old_code = ticket.code
        ticket.code = _new_code()
        ticket.access_token = _access_token()
        ticket.holder = recipient
        ticket.attendee_name = to_name
        ticket.attendee_phone = to.value if not to.is_email else ""
        ticket.attendee_email = to.value if to.is_email else ""
        ticket.transferred_at = timezone.now()
        ticket.save()
        TicketTransfer.objects.create(
            ticket=ticket, from_user=by_user, to_user=recipient, to_name=to_name,
            to_contact=to.value, old_code=old_code, new_code=ticket.code,
        )
        sender = by_user.full_name or "A friend"
        transaction.on_commit(lambda: deliver_transfer_notice.delay(ticket.pk, sender))
    return ticket
