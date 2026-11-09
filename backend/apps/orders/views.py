import hmac

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.dispatch import dispatch
from apps.events.models import Event
from apps.notifications.tasks import deliver_order_confirmation
from apps.payments.gateways import GatewayError
from apps.payments.models import Payment
from apps.payments.services import confirm_payment, start_payment

from . import serializers as s
from .models import Order, OrderStatus
from .services import CheckoutError, create_order


def _order_qs():
    return Order.objects.select_related("event__venue", "promo_code").prefetch_related(
        "items__ticket_type", Prefetch("payments", queryset=Payment.objects.order_by("-created_at"))
    )


def _load_order(request, reference) -> Order:
    """Owner (signed in) or anyone holding the order's access token may see it."""
    order = get_object_or_404(_order_qs(), reference=reference.upper())
    if request.user.is_authenticated and order.user_id == request.user.id:
        return order
    token = request.query_params.get("token", "")
    if not token and hasattr(request.data, "get"):
        token = request.data.get("token", "")
    if token and hmac.compare_digest(str(token), order.access_token):
        return order
    raise NotFound()


_TOKEN_PARAM = OpenApiParameter("token", str, description="Order access token (guest buyers)")


class CheckoutView(APIView):
    """
    Reserve tickets and start payment. Works for guests (no account needed).

    Returns the order and, for paid orders, `payment.authorization_url`:
    send the buyer there to pay with Mobile Money or card. Tickets are held
    for ORDER_HOLD_MINUTES. Free orders come back already `paid`.
    """

    permission_classes = [AllowAny]
    throttle_scope = "checkout"

    @extend_schema(request=s.CheckoutSerializer, responses={201: s.OrderSerializer})
    def post(self, request):
        ser = s.CheckoutSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        event = Event.objects.select_related("organization").filter(slug=data["event"]).first()
        if event is None:
            raise ValidationError({"event": ["Event not found."]})
        try:
            order = create_order(
                event=event, items=data["items"], buyer=data["buyer"],
                user=request.user, promo_code=data.get("promo_code", ""), ref=data.get("ref", ""),
            )
        except CheckoutError as exc:
            raise ValidationError({exc.field: [exc.message]})

        if order.status == OrderStatus.PENDING:
            try:
                start_payment(order)
            except GatewayError:
                order.status = OrderStatus.FAILED
                order.save(update_fields=["status", "updated_at"])
                return Response(
                    {"detail": "We couldn't start the payment. Please try again."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        order = _order_qs().get(pk=order.pk)
        return Response(s.OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class MyOrdersView(generics.ListAPIView):
    """Orders placed by (or claimed by) the signed-in user."""

    serializer_class = s.OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _order_qs().filter(user=self.request.user).exclude(status=OrderStatus.EXPIRED)


class OrderDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(parameters=[_TOKEN_PARAM], responses=s.OrderSerializer)
    def get(self, request, reference):
        return Response(s.OrderSerializer(_load_order(request, reference)).data)


class OrderVerifyView(APIView):
    """
    Call after the buyer returns from the payment page. Checks with the
    gateway and issues tickets if the payment succeeded. Safe to repeat.
    """

    permission_classes = [AllowAny]

    @extend_schema(parameters=[_TOKEN_PARAM], request=None, responses=s.OrderSerializer)
    def post(self, request, reference):
        order = _load_order(request, reference)
        payment = order.payments.order_by("-created_at").first()
        if payment is not None and order.status in (OrderStatus.PENDING, OrderStatus.EXPIRED):
            try:
                confirm_payment(payment)
            except GatewayError:
                return Response(
                    {"detail": "We couldn't confirm the payment yet. Please try again shortly."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response(s.OrderSerializer(_order_qs().get(pk=order.pk)).data)


class OrderRetryPaymentView(APIView):
    """Start a new payment attempt (e.g. MoMo prompt declined) while the hold is still active."""

    permission_classes = [AllowAny]

    @extend_schema(parameters=[_TOKEN_PARAM], request=None, responses=s.OrderSerializer)
    def post(self, request, reference):
        order = _load_order(request, reference)
        if not order.is_hold_active:
            raise ValidationError({"detail": "This order is no longer awaiting payment. Please start again."})
        try:
            start_payment(order)
        except GatewayError:
            return Response(
                {"detail": "We couldn't start the payment. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(s.OrderSerializer(_order_qs().get(pk=order.pk)).data)


class OrderResendView(APIView):
    """Re-send the tickets by SMS and email (limited to a few times per hour)."""

    permission_classes = [AllowAny]
    throttle_scope = "resend"

    @extend_schema(parameters=[_TOKEN_PARAM], request=None, responses={202: None})
    def post(self, request, reference):
        order = _load_order(request, reference)
        if order.status != OrderStatus.PAID:
            raise ValidationError({"detail": "Tickets are sent once the order is paid."})
        dispatch(deliver_order_confirmation, order.pk)
        return Response({"detail": "Tickets re-sent."}, status=status.HTTP_202_ACCEPTED)
