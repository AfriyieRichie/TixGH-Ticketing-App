"""
Buyer-facing messages. Every send is logged in `Delivery`; a failed SMS or
email never breaks the purchase itself.
"""

import logging
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.core.messaging import send_sms
from apps.orders.models import Order, OrderStatus, Ticket
from apps.tickets.rendering import format_when, format_where, tickets_pdf

from .models import Delivery, DeliveryStatus

logger = logging.getLogger(__name__)


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _log(kind, channel, to, order, fn) -> bool:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - any provider failure is logged, never raised
        logger.exception("%s %s to %s failed", kind, channel, to)
        Delivery.objects.create(order=order, kind=kind, channel=channel, to=to,
                                status=DeliveryStatus.FAILED, error=str(exc)[:500])
        return False
    Delivery.objects.create(order=order, kind=kind, channel=channel, to=to, status=DeliveryStatus.SENT)
    return True


def _email(to, subject, template, ctx, attachments=()):
    ctx = {"platform": settings.PLATFORM_NAME, **ctx}
    html = render_to_string(f"notifications/{template}.html", ctx)
    text = render_to_string(f"notifications/{template}.txt", ctx)
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    msg.attach_alternative(html, "text/html")
    for name, content, mime in attachments:
        msg.attach(name, content, mime)
    msg.send()


def whatsapp_share_url(order: Order) -> str:
    text = f"My tickets for {order.event.title} ({format_when(order.event)}): {order.tickets_url}"
    return f"https://wa.me/?text={quote(text)}"


# --------------------------------------------------------------------------
def send_order_confirmation(order: Order) -> None:
    order = Order.objects.select_related("event__venue").get(pk=order.pk)
    if order.status != OrderStatus.PAID:
        return
    tickets = list(order.tickets.select_related("ticket_type", "event__venue", "order"))
    ev = order.event
    n = len(tickets)
    if order.buyer_phone:
        sms = (
            f"{settings.PLATFORM_NAME}: Your {n} ticket{'s' if n > 1 else ''} for {_short(ev.title)}, "
            f"{format_when(ev)}. Show the QR at the gate: {order.tickets_url}"
        )
        _log("order_confirmation", "sms", order.buyer_phone, order, lambda: send_sms(order.buyer_phone, sms))
    if order.buyer_email:
        ctx = {"order": order, "event": ev, "tickets": tickets, "when": format_when(ev), "where": format_where(ev)}
        _log(
            "order_confirmation", "email", order.buyer_email, order,
            lambda: _email(
                order.buyer_email, f"Your tickets: {ev.title}", "order_confirmation", ctx,
                attachments=[(f"tickets-{order.reference}.pdf", tickets_pdf(tickets), "application/pdf")],
            ),
        )


def send_transfer_notice(ticket: Ticket, from_name: str) -> None:
    ticket = Ticket.objects.select_related("event__venue", "ticket_type", "order").get(pk=ticket.pk)
    ev = ticket.event
    who = from_name or "Someone"
    if ticket.attendee_phone:
        sms = (
            f"{settings.PLATFORM_NAME}: {who} sent you a {ticket.ticket_type.name} ticket for "
            f"{_short(ev.title)}, {format_when(ev)}. View it: {ticket.page_url}"
        )
        _log("transfer", "sms", ticket.attendee_phone, ticket.order,
             lambda: send_sms(ticket.attendee_phone, sms))
    if ticket.attendee_email:
        ctx = {"ticket": ticket, "event": ev, "from_name": who, "when": format_when(ev), "where": format_where(ev)}
        _log("transfer", "email", ticket.attendee_email, ticket.order,
             lambda: _email(ticket.attendee_email, f"{who} sent you a ticket: {ev.title}", "transfer", ctx,
                            attachments=[(f"ticket-{ticket.code}.pdf", tickets_pdf([ticket]), "application/pdf")]))


def notify_event_cancelled(event) -> int:
    """Tell every paying buyer. Returns the number of orders notified."""
    orders = Order.objects.filter(event=event, status=OrderStatus.PAID)
    for order in orders:
        sms = (
            f"{settings.PLATFORM_NAME}: Sorry, {_short(event.title)} on {format_when(event)} has been cancelled "
            f"by the organizer. Your refund for order {order.reference} will be processed. "
            "We'll send you an SMS when it's done."
        )
        if order.buyer_phone:
            _log("cancellation", "sms", order.buyer_phone, order, lambda o=order, m=sms: send_sms(o.buyer_phone, m))
        if order.buyer_email:
            ctx = {"order": order, "event": event, "when": format_when(event), "reason": event.cancellation_reason}
            _log("cancellation", "email", order.buyer_email, order,
                 lambda o=order, c=ctx: _email(o.buyer_email, f"Cancelled: {event.title}", "cancellation", c))
    return orders.count()


def send_due_reminders(window_hours: int = 24) -> int:
    """Remind buyers of events starting within the next `window_hours`."""
    now = timezone.now()
    orders = Order.objects.select_related("event__venue").filter(
        status=OrderStatus.PAID, reminder_sent_at__isnull=True,
        event__status="published", event__start_at__gt=now,
        event__start_at__lte=now + timedelta(hours=window_hours),
    )
    count = 0
    for order in orders:
        ev = order.event
        if order.buyer_phone:
            sms = (
                f"{settings.PLATFORM_NAME} reminder: {_short(ev.title)} is on {format_when(ev)} at "
                f"{_short(format_where(ev), 50)}. Your tickets: {order.tickets_url}"
            )
            _log("reminder", "sms", order.buyer_phone, order, lambda o=order, m=sms: send_sms(o.buyer_phone, m))
        if order.buyer_email:
            ctx = {"order": order, "event": ev, "when": format_when(ev), "where": format_where(ev)}
            _log("reminder", "email", order.buyer_email, order,
                 lambda o=order, c=ctx: _email(o.buyer_email, f"Reminder: {ev.title} is coming up", "reminder", c))
        order.reminder_sent_at = now
        order.save(update_fields=["reminder_sent_at", "updated_at"])
        count += 1
    return count
