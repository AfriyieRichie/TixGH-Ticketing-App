"""
Refunds.

Who gets what back (agreed business rules):
- Event cancelled by the organizer: everything the buyer paid, booking fee included.
- Organizer refunds a ticket/order, or a buyer requests one within the event's
  refund policy: the ticket price only; the booking fee is non-refundable.

For each refund we record how much comes back out of the organizer's earnings
and how much out of the platform's fees, so dashboards and payouts stay right.
Refunded tickets are voided and, if the event hasn't happened, go back on sale.

The money itself is returned by the payment gateway (Paystack) in the
background: queued, retried up to 3 times, then its final status is polled.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.dispatch import dispatch
from apps.events.models import EventStatus, RefundPolicy, TicketType
from apps.notifications.tasks import deliver_refund_notice
from apps.orders.models import Order, OrderStatus, Ticket, TicketStatus

from .gateways import GatewayError, get_gateway
from .models import PaymentStatus, Refund, RefundKind, RefundStatus
from .tasks import process_refund_task

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
POLICY_DAYS = {RefundPolicy.UP_TO_1_DAY: 1, RefundPolicy.UP_TO_7_DAYS: 7, RefundPolicy.UP_TO_30_DAYS: 30}


class RefundError(Exception):
    pass


# --------------------------------------------------------------------------
# Buyer self-service
# --------------------------------------------------------------------------
def buyer_refund_deadline(event):
    days = POLICY_DAYS.get(event.refund_policy)
    return event.start_at - timedelta(days=days) if days else None


def _buyer_refundable_tickets(order) -> list[Ticket]:
    # Not used, not void, and not given away to someone else.
    return list(order.tickets.filter(status=TicketStatus.VALID, transferred_at__isnull=True)
                .select_related("order_item"))


def buyer_refund_quote(order: Order) -> dict:
    ev = order.event
    deadline = buyer_refund_deadline(ev)
    tickets = _buyer_refundable_tickets(order)
    amount = sum((t.order_item.unit_price for t in tickets), Decimal("0"))
    reason = ""
    if order.status != OrderStatus.PAID:
        reason = "This order can't be refunded."
    elif ev.status == EventStatus.CANCELLED:
        reason = "This event was cancelled: you're refunded automatically."
    elif deadline is None:
        reason = "The organizer doesn't offer refunds for this event."
    elif timezone.now() > deadline:
        reason = f"Refunds closed on {timezone.localtime(deadline):%d %b %Y, %H:%M}."
    elif not tickets:
        reason = "No unused tickets left to refund."
    return {
        "eligible": not reason, "reason": reason, "deadline": deadline,
        "amount": str(amount), "tickets": [t.code for t in tickets],
        "booking_fee_refunded": False,
    }


# --------------------------------------------------------------------------
# Creating refunds
# --------------------------------------------------------------------------
def create_refund(order: Order, *, kind: str, tickets: list[Ticket] | None = None, reason: str = "",
                  by_user=None) -> Refund:
    """Void the tickets, adjust stock and totals, and queue the money back to the buyer."""
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related("event").get(pk=order.pk)
        if order.status != OrderStatus.PAID:
            raise RefundError("Only paid orders can be refunded.")
        available = {t.pk: t for t in order.tickets.exclude(status=TicketStatus.VOID).select_related("order_item")}
        if tickets is None:
            chosen = list(available.values())
        else:
            if any(t.pk not in available for t in tickets):
                raise RefundError("Some of those tickets aren't refundable (wrong order or already refunded).")
            chosen = [available[t.pk] for t in tickets]
        if not chosen:
            raise RefundError("Nothing left to refund on this order.")

        include_fees = kind == RefundKind.CANCELLATION
        amount = platform = Decimal("0")
        for t in chosen:
            item = t.order_item
            buyer_paid_fee = order.fee_bearer == "buyer"
            amount += item.unit_price + (item.unit_fee if include_fees and buyer_paid_fee else 0)
            platform += item.unit_fee if include_fees else 0
        amount = min(amount, order.total - order.refunded_amount)
        platform = min(platform, amount)

        # Void tickets; return seats to sale if the event is still ahead.
        Ticket.objects.filter(pk__in=[t.pk for t in chosen]).update(
            status=TicketStatus.VOID, inside=0, updated_at=timezone.now()
        )
        ev = order.event
        if ev.status == EventStatus.PUBLISHED and not ev.has_ended:
            per_type: dict[int, int] = {}
            for t in chosen:
                per_type[t.ticket_type_id] = per_type.get(t.ticket_type_id, 0) + 1
            for type_id, n in per_type.items():
                TicketType.objects.filter(pk=type_id).update(quantity_sold=F("quantity_sold") - n)

        order.refunded_amount += amount
        if not order.tickets.exclude(status=TicketStatus.VOID).exists():
            order.status = OrderStatus.REFUNDED
        order.save(update_fields=["refunded_amount", "status", "updated_at"])

        payment = order.payments.filter(status=PaymentStatus.SUCCESS).order_by("-paid_at").first()
        refund = Refund.objects.create(
            order=order, payment=payment, kind=kind, amount=amount, organizer_amount=amount - platform,
            platform_amount=platform, reason=reason[:500], requested_by=by_user,
            status=RefundStatus.PROCESSED if amount == 0 else RefundStatus.PENDING,
            processed_at=timezone.now() if amount == 0 else None,
        )
        refund.tickets.set(chosen)
        refund_id = refund.pk
        if amount > 0:
            transaction.on_commit(lambda: dispatch(process_refund_task, refund_id))
        transaction.on_commit(lambda: dispatch(deliver_refund_notice, refund_id))
    return refund


def request_buyer_refund(order: Order, by_user=None) -> Refund:
    quote = buyer_refund_quote(order)
    if not quote["eligible"]:
        raise RefundError(quote["reason"])
    tickets = list(order.tickets.filter(code__in=quote["tickets"]))
    return create_refund(order, kind=RefundKind.BUYER_REQUEST, tickets=tickets,
                         reason="Requested by buyer", by_user=by_user)


def refund_cancelled_event(event) -> int:
    """Refund every paid order of a cancelled event in full. Returns how many orders."""
    count = 0
    for order in Order.objects.filter(event=event, status=OrderStatus.PAID):
        try:
            create_refund(order, kind=RefundKind.CANCELLATION, reason="Event cancelled")
            count += 1
        except RefundError:
            logger.exception("Couldn't refund order %s of cancelled event %s", order.reference, event.pk)
    return count


# --------------------------------------------------------------------------
# Talking to the gateway
# --------------------------------------------------------------------------
def process_refund(refund: Refund) -> Refund:
    with transaction.atomic():
        refund = Refund.objects.select_for_update().select_related("payment", "order").get(pk=refund.pk)
        if refund.status not in (RefundStatus.PENDING,):
            return refund
        refund.attempts += 1
        if refund.payment is None:
            refund.status, refund.error = RefundStatus.FAILED, "No successful payment found for this order."
            refund.save(update_fields=["status", "error", "attempts"])
            return refund
        try:
            result = get_gateway(refund.payment.gateway).refund(
                refund.payment, refund.amount, note=f"{refund.get_kind_display()} {refund.order.reference}"
            )
        except GatewayError as exc:
            refund.error = str(exc)[:500]
            refund.status = RefundStatus.FAILED if refund.attempts >= MAX_ATTEMPTS else RefundStatus.PENDING
            refund.save(update_fields=["status", "error", "attempts"])
            logger.warning("Refund %s attempt %s failed: %s", refund.pk, refund.attempts, exc)
            return refund
        refund.gateway_reference = result.reference
        refund.status = {"processed": RefundStatus.PROCESSED, "failed": RefundStatus.FAILED}.get(
            result.status, RefundStatus.PROCESSING)
        if refund.status == RefundStatus.PROCESSED:
            refund.processed_at = timezone.now()
        refund.error = ""
        refund.save(update_fields=["status", "gateway_reference", "processed_at", "error", "attempts"])
    return refund


def check_refunds() -> dict:
    """Retry queued refunds and poll ones the gateway is still processing (runs on the scheduler)."""
    retried = polled = 0
    for r in Refund.objects.filter(status=RefundStatus.PENDING, amount__gt=0):
        process_refund(r)
        retried += 1
    for r in Refund.objects.filter(status=RefundStatus.PROCESSING).select_related("payment"):
        try:
            state = get_gateway(r.payment.gateway).refund_status(r.gateway_reference)
        except GatewayError:
            continue
        if state == "processed":
            r.status, r.processed_at = RefundStatus.PROCESSED, timezone.now()
        elif state == "failed":
            r.status = RefundStatus.FAILED
        r.save(update_fields=["status", "processed_at"])
        polled += 1
    return {"retried": retried, "polled": polled}
