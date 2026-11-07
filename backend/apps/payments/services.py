import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderStatus
from apps.orders.services import fulfil_order

from .gateways import GatewayError, Split, get_gateway
from .models import Payment, PaymentStatus

logger = logging.getLogger(__name__)


def _payer_email(order: Order, fallback_domain: str) -> str:
    if order.buyer_email:
        return order.buyer_email
    digits = "".join(c for c in order.buyer_phone if c.isdigit()) or order.reference.lower()
    return f"{digits}@{fallback_domain}"


def start_payment(order: Order) -> Payment:
    """Create a payment attempt and get the gateway checkout URL. Raises GatewayError."""
    gateway = get_gateway()
    split = None
    payout = order.event.organization.payout_accounts.filter(is_default=True).first()
    if payout is not None:
        try:
            split = Split(gateway.ensure_subaccount(payout), order.platform_amount)
        except GatewayError:
            # Fall back to collecting everything; the organizer is paid out manually.
            logger.exception("Could not set up split for org %s", order.event.organization_id)

    payment = Payment.objects.create(order=order, gateway=gateway.name, amount=order.total, currency=order.currency)
    try:
        init = gateway.initialize(payment, _payer_email(order, settings.PAYSTACK_FALLBACK_EMAIL_DOMAIN), split)
    except GatewayError:
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=["status", "updated_at"])
        raise
    payment.authorization_url = init.authorization_url
    payment.access_code = init.access_code
    payment.save(update_fields=["authorization_url", "access_code", "updated_at"])
    return payment


def confirm_payment(payment: Payment) -> Payment:
    """
    Ask the gateway whether `payment` succeeded and, if so, fulfil the order.
    Idempotent: webhooks and buyer redirects may both call this.
    """
    gateway = get_gateway(payment.gateway)
    result = gateway.verify(payment)  # network call outside the DB lock

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status == PaymentStatus.SUCCESS:
            pass  # already recorded; still make sure the order is fulfilled below
        elif result.status == "success":
            if result.currency != payment.currency:
                logger.error("Currency mismatch on %s: %s", payment.reference, result.currency)
            payment.status = PaymentStatus.SUCCESS
            payment.amount_paid = result.amount
            payment.channel = result.channel
            payment.paid_at = timezone.now()
            payment.gateway_response = {**payment.gateway_response, "verify": result.raw}
            payment.save()
        elif result.status in ("failed", "abandoned"):
            payment.status = result.status
            payment.gateway_response = {**payment.gateway_response, "verify": result.raw}
            payment.save(update_fields=["status", "gateway_response", "updated_at"])
            return payment
        else:
            return payment  # still pending

    order = payment.order
    if order.status != OrderStatus.PAID:
        fulfil_order(order, amount_paid=payment.amount_paid)
    return payment
