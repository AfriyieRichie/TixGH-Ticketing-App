"""
Checkout rules. Ticket stock is protected in two layers:

1. Soft holds: a pending (unpaid) order reserves its tickets until
   `expires_at`. Availability = quantity - sold - active holds.
2. Hard limit: `quantity_sold <= quantity` is a database constraint, and
   ticket-type rows are locked (SELECT ... FOR UPDATE) while reserving or
   fulfilling, so two buyers can never get the same last ticket.
"""

import logging
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.core.dispatch import dispatch
from apps.events.models import Event, PromoCode, TicketType, TicketVisibility
from apps.events.pricing import price_breakdown
from apps.notifications.tasks import deliver_order_confirmation

from .models import Order, OrderItem, OrderStatus, Ticket

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    def __init__(self, message: str, field: str = "detail"):
        super().__init__(message)
        self.message, self.field = message, field


def held_quantities(ticket_type_ids, exclude_order: Order | None = None) -> dict[int, int]:
    """Tickets reserved by unpaid orders whose hold hasn't expired, per ticket type."""
    qs = OrderItem.objects.filter(
        ticket_type_id__in=ticket_type_ids,
        order__status=OrderStatus.PENDING,
        order__expires_at__gt=timezone.now(),
    )
    if exclude_order is not None:
        qs = qs.exclude(order=exclude_order)
    return {
        row["ticket_type_id"]: row["n"]
        for row in qs.values("ticket_type_id").annotate(n=Sum("quantity"))
    }


def _promo_pending_uses(promo: PromoCode) -> int:
    return Order.objects.filter(
        promo_code=promo, status=OrderStatus.PENDING, expires_at__gt=timezone.now()
    ).count()


def create_order(*, event: Event, items: list[dict], buyer: dict, user=None, promo_code: str = "") -> Order:
    """
    Reserve tickets and create a pending order. Free orders are completed
    immediately. `items` = [{"ticket_type": id, "quantity": n}, ...].
    Raises CheckoutError.
    """
    if not event.is_live:
        raise CheckoutError("Tickets for this event are not on sale.")

    wanted = Counter()
    for it in items:
        wanted[int(it["ticket_type"])] += int(it["quantity"])
    wanted = +wanted  # drop zero quantities
    if not wanted:
        raise CheckoutError("Choose at least one ticket.", "items")
    if sum(wanted.values()) > event.max_tickets_per_order:
        raise CheckoutError(f"You can buy at most {event.max_tickets_per_order} tickets per order.", "items")

    now = timezone.now()
    with transaction.atomic():
        types = {
            t.pk: t
            for t in TicketType.objects.select_for_update()
            .select_related("event__organization")
            .filter(event=event, pk__in=wanted.keys())
        }
        if missing := set(wanted) - set(types):
            raise CheckoutError(f"Ticket type(s) {sorted(missing)} are not part of this event.", "items")

        promo = None
        if promo_code:
            promo = (
                PromoCode.objects.select_for_update()
                .prefetch_related("ticket_types")
                .filter(event=event, code=promo_code.strip().upper())
                .first()
            )
            if promo is None:
                raise CheckoutError("This code isn't valid for this event.", "promo_code")
            if problem := promo.problem():
                raise CheckoutError(problem, "promo_code")
            if promo.max_uses is not None and promo.times_used + _promo_pending_uses(promo) >= promo.max_uses:
                raise CheckoutError("This code has been fully used.", "promo_code")
            if not any(promo.applies_to(types[i]) for i in wanted):
                raise CheckoutError("This code doesn't apply to the tickets you selected.", "promo_code")

        held = held_quantities(wanted.keys())
        lines = []
        for type_id, qty in wanted.items():
            t = types[type_id]
            if t.visibility == TicketVisibility.HIDDEN and not (promo and promo.applies_to(t)):
                raise CheckoutError(f"'{t.name}' requires an access code.", "items")
            status = t.sale_status
            if status != "on_sale" and status != "sold_out":
                messages = {"scheduled": "is not on sale yet", "ended": "is no longer on sale"}
                raise CheckoutError(f"'{t.name}' {messages.get(status, 'is not available')}.", "items")
            available = t.quantity - t.quantity_sold - held.get(t.pk, 0)
            if qty > available:
                msg = f"Only {available} '{t.name}' ticket(s) left." if available > 0 else f"'{t.name}' is sold out."
                raise CheckoutError(msg, "items")
            if qty < t.min_per_order or qty > t.max_per_order:
                raise CheckoutError(
                    f"'{t.name}': choose between {t.min_per_order} and {t.max_per_order} tickets.", "items"
                )
            unit_price = promo.discounted_price(t.price) if promo and promo.applies_to(t) else t.price
            lines.append((t, qty, unit_price, price_breakdown(event, unit_price)))

        subtotal = sum(unit_price * qty for _, qty, unit_price, _ in lines)
        list_total = sum(t.price * qty for t, qty, _, _ in lines)
        fee_total = sum(b.fee * qty for _, qty, _, b in lines)
        total = sum(b.buyer_pays * qty for _, qty, _, b in lines)
        organizer_amount = sum(b.organizer_receives * qty for _, qty, _, b in lines)

        order = Order.objects.create(
            event=event,
            user=user if user and user.is_authenticated else None,
            buyer_name=buyer["full_name"],
            buyer_email=buyer.get("email") or "",
            buyer_phone=buyer.get("phone") or "",
            buyer_organization=(buyer.get("organization") or "").strip(),
            buyer_job_title=(buyer.get("job_title") or "").strip(),
            share_contact=bool(buyer.get("share_contact")) and event.badges_enabled,
            promo_code=promo,
            fee_bearer=event.effective_fee_bearer,
            subtotal=subtotal,
            discount_total=list_total - subtotal,
            fee_total=fee_total,
            total=total,
            organizer_amount=organizer_amount,
            platform_amount=total - organizer_amount,
            expires_at=now + timedelta(minutes=settings.ORDER_HOLD_MINUTES),
        )
        OrderItem.objects.bulk_create(
            OrderItem(
                order=order, ticket_type=t, quantity=qty,
                unit_list_price=t.price, unit_price=unit_price, unit_fee=b.fee,
                unit_buyer_pays=b.buyer_pays, unit_organizer_receives=b.organizer_receives,
            )
            for t, qty, unit_price, b in lines
        )

    if order.total == 0:
        order = fulfil_order(order, amount_paid=Decimal("0.00"))
    return order


def _flag(order: Order, note: str) -> Order:
    logger.error("Order %s needs review: %s", order.reference, note)
    order.status = OrderStatus.NEEDS_REVIEW
    order.review_note = note
    order.save(update_fields=["status", "review_note", "updated_at"])
    return order


def fulfil_order(order: Order, amount_paid: Decimal | None) -> Order:
    """
    Mark an order paid and issue its tickets. Safe to call more than once
    (e.g. from both the webhook and the buyer's redirect).
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status in (OrderStatus.PAID, OrderStatus.NEEDS_REVIEW, OrderStatus.REFUNDED):
            return order
        if order.status == OrderStatus.CANCELLED:
            return _flag(order, "Payment received for a cancelled order. Refund the buyer.")
        if amount_paid is not None and amount_paid != order.total:
            return _flag(order, f"Amount paid ({amount_paid}) does not match order total ({order.total}).")

        items = list(order.items.all())
        type_ids = [i.ticket_type_id for i in items]
        types = {t.pk: t for t in TicketType.objects.select_for_update().filter(pk__in=type_ids)}
        hold_active = order.status == OrderStatus.PENDING and timezone.now() < order.expires_at
        # If the hold lapsed, other buyers' active holds take priority.
        others = {} if hold_active else held_quantities(type_ids, exclude_order=order)
        for item in items:
            t = types[item.ticket_type_id]
            if item.quantity > t.quantity - t.quantity_sold - others.get(t.pk, 0):
                return _flag(order, f"'{t.name}' sold out before payment completed. Refund the buyer.")

        for item in items:
            TicketType.objects.filter(pk=item.ticket_type_id).update(quantity_sold=F("quantity_sold") + item.quantity)
        Ticket.objects.bulk_create(
            Ticket(
                order=order, order_item=item, event_id=order.event_id, ticket_type_id=item.ticket_type_id,
                holder=order.user, attendee_name=order.buyer_name,
                attendee_organization=order.buyer_organization, attendee_job_title=order.buyer_job_title,
                share_contact=order.share_contact,
            )
            for item in items
            for _ in range(item.quantity)
        )
        if order.promo_code_id:
            PromoCode.objects.filter(pk=order.promo_code_id).update(times_used=F("times_used") + 1)
        order.status = OrderStatus.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])
        order_pk = order.pk
        transaction.on_commit(lambda: dispatch(deliver_order_confirmation, order_pk))
    logger.info("Order %s paid; %s ticket(s) issued", order.reference, order.ticket_count)
    return order


def expire_stale_orders() -> int:
    """Mark unpaid orders past their hold as expired. Returns how many."""
    return Order.objects.filter(status=OrderStatus.PENDING, expires_at__lte=timezone.now()).update(
        status=OrderStatus.EXPIRED, updated_at=timezone.now()
    )


def claim_guest_orders(user) -> int:
    """Attach guest orders to a user whose email/phone has just been verified."""
    q = Q()
    if user.phone and user.phone_verified:
        q |= Q(buyer_phone=user.phone)
    if user.email and user.email_verified:
        q |= Q(buyer_email__iexact=user.email)
    if not q:
        return 0
    orders = Order.objects.filter(q, user__isnull=True)
    ids = list(orders.values_list("pk", flat=True))
    if ids:
        Order.objects.filter(pk__in=ids).update(user=user)
        Ticket.objects.filter(order_id__in=ids, holder__isnull=True, transferred_at__isnull=True).update(holder=user)
    # Tickets someone transferred to this phone/email before they had an account.
    tq = Q()
    if user.phone and user.phone_verified:
        tq |= Q(attendee_phone=user.phone)
    if user.email and user.email_verified:
        tq |= Q(attendee_email__iexact=user.email)
    if tq:
        Ticket.objects.filter(tq, holder__isnull=True, transferred_at__isnull=False).update(holder=user)
    return len(ids)
