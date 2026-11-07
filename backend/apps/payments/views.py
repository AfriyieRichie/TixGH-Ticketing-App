import logging
from html import escape

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import OrderStatus

from django.core.cache import cache

from .gateways import GatewayError, PaystackGateway, get_gateway
from .models import Payment
from .services import confirm_payment

logger = logging.getLogger(__name__)


class PaystackWebhookView(APIView):
    """Paystack calls this when a payment succeeds. Signature-checked."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def post(self, request):
        if settings.PAYMENT_GATEWAY != "paystack":
            raise Http404
        reference = PaystackGateway().webhook_reference(request)
        if reference:
            payment = Payment.objects.filter(reference=reference).first()
            if payment is None:
                logger.warning("Webhook for unknown payment %s", reference)
            else:
                try:
                    confirm_payment(payment)
                except GatewayError:
                    logger.exception("Webhook confirm failed for %s", reference)
                    return Response(status=500)  # Paystack will retry
        return Response(status=200)


class BankListView(APIView):
    """Ghana banks for organizer payout accounts (cached for a day)."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}})
    def get(self, request):
        key = f"banks:{settings.PAYMENT_GATEWAY}"
        banks = cache.get(key)
        if banks is None:
            try:
                banks = get_gateway().list_banks()
            except GatewayError:
                return Response({"detail": "Bank list unavailable right now."}, status=503)
            cache.set(key, banks, 60 * 60 * 24)
        return Response(banks)


# --------------------------------------------------------------------------
# Simulated gateway checkout page (development only)
# --------------------------------------------------------------------------
_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simulated payment</title>
<style>
body{{font-family:system-ui,sans-serif;background:#f4f4f5;margin:0;padding:24px;color:#18181b}}
.card{{max-width:420px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px #0002}}
.badge{{display:inline-block;background:#fef3c7;color:#92400e;font-size:12px;padding:4px 8px;border-radius:6px}}
h1{{font-size:20px;margin:12px 0 4px}} .amt{{font-size:32px;font-weight:700;margin:16px 0}}
button{{width:100%;padding:14px;margin-top:10px;border:0;border-radius:8px;font-size:16px;cursor:pointer}}
.ok{{background:#16a34a;color:#fff}} .card-btn{{background:#2563eb;color:#fff}} .no{{background:#e4e4e7}}
.muted{{color:#71717a;font-size:14px}} a{{color:#2563eb}}
</style></head><body><div class="card">{body}</div></body></html>"""


def _render(body: str, status=200) -> HttpResponse:
    return HttpResponse(_PAGE.format(body=body), status=status)


@csrf_exempt
def simulated_checkout(request, reference):
    if settings.PAYMENT_GATEWAY != "simulated":
        raise Http404
    payment = get_object_or_404(Payment.objects.select_related("order__event"), reference=reference, gateway="simulated")
    order = payment.order
    head = (
        '<span class="badge">TEST MODE: no real money</span>'
        f"<h1>{escape(order.event.title)}</h1>"
        f'<div class="muted">Order {order.reference} · {escape(order.buyer_name)}</div>'
        f'<div class="amt">GHS {order.total}</div>'
    )
    if request.method == "POST":
        outcome = request.POST.get("outcome")
        if payment.status == "initialized" and outcome in ("success", "failed"):
            payment.gateway_response = {
                **payment.gateway_response,
                "simulated_outcome": outcome,
                "simulated_channel": request.POST.get("channel", "mobile_money"),
            }
            payment.save(update_fields=["gateway_response", "updated_at"])
            confirm_payment(payment)
            order.refresh_from_db()
        if order.status == OrderStatus.PAID:
            codes = ", ".join(t.code for t in order.tickets.all())
            result = f"<p><b>✅ Payment successful.</b></p><p class='muted'>Ticket codes: {codes}</p>"
        elif order.status == OrderStatus.NEEDS_REVIEW:
            result = f"<p><b>⚠️ Paid, but needs review:</b> {escape(order.review_note)}</p>"
        else:
            result = "<p><b>❌ Payment declined.</b> You can retry while your tickets are held.</p>"
        back = f"{settings.PAYMENT_CALLBACK_URL}?reference={order.reference}"
        return _render(head + result + f'<p><a href="{back}">Return to the site</a></p>')

    if payment.status != "initialized":
        return _render(head + f"<p>This payment is already <b>{payment.status}</b>.</p>")
    form = """
      <form method="post"><input type="hidden" name="outcome" value="success">
        <input type="hidden" name="channel" value="mobile_money">
        <button class="ok">Pay with Mobile Money</button></form>
      <form method="post"><input type="hidden" name="outcome" value="success">
        <input type="hidden" name="channel" value="card">
        <button class="card-btn">Pay with card</button></form>
      <form method="post"><input type="hidden" name="outcome" value="failed">
        <button class="no">Decline / cancel</button></form>"""
    return _render(head + form)
