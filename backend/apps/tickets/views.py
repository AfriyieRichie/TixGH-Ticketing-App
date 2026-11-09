import hmac

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import ContactField
from apps.orders.models import Order, OrderStatus, Ticket, TicketStatus

from .rendering import format_when, format_where, qr_svg, tickets_pdf
from .services import TransferError, transfer_ticket

TICKET_RELATED = ("event__venue", "event__organization", "ticket_type", "order")


# --------------------------------------------------------------------------
# Wallet API (signed-in users)
# --------------------------------------------------------------------------
class WalletTicketSerializer(serializers.ModelSerializer):
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)
    admits = serializers.IntegerField(source="ticket_type.admits", read_only=True)
    qr_payload = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    page_url = serializers.CharField(read_only=True)
    can_transfer = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "code", "qr_payload", "ticket_type_name", "admits", "attendee_name", "status",
            "checked_in_at", "event", "page_url", "can_transfer", "issued_at",
        ]
        read_only_fields = [f for f in fields if f != "attendee_name"]

    def get_qr_payload(self, obj) -> str | None:
        return obj.qr_payload if obj.qr_active else None

    def get_event(self, obj) -> dict:
        ev = obj.event
        return {
            "slug": ev.slug, "title": ev.title, "start_at": ev.start_at, "end_at": ev.end_at,
            "status": ev.status, "when": format_when(ev), "where": format_where(ev),
            "cover_image": ev.cover_image.url if ev.cover_image else None,
            "online_url": ev.online_url if obj.status == TicketStatus.VALID else "",
        }

    def get_can_transfer(self, obj) -> bool:
        ev = obj.event
        return obj.status == TicketStatus.VALID and ev.allow_transfers and ev.status == "published" and not ev.has_ended


class TransferSerializer(serializers.Serializer):
    to = ContactField(help_text="Recipient's phone number or email")
    name = serializers.CharField(max_length=150)


class WalletListView(generics.ListAPIView):
    """My tickets. ?when=upcoming (default) | past | all"""

    serializer_class = WalletTicketSerializer

    @extend_schema(parameters=[OpenApiParameter("when", str, enum=["upcoming", "past", "all"])])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Ticket.objects.select_related(*TICKET_RELATED).filter(holder=self.request.user).exclude(
            status=TicketStatus.VOID
        )
        when = self.request.query_params.get("when", "upcoming")
        now = timezone.now()
        if when == "upcoming":
            return qs.filter(event__end_at__gte=now).order_by("event__start_at", "id")
        if when == "past":
            return qs.filter(event__end_at__lt=now).order_by("-event__start_at", "id")
        return qs.order_by("-event__start_at", "id")


class WalletTicketView(generics.RetrieveUpdateAPIView):
    """One of my tickets. PATCH to set the attendee's name."""

    serializer_class = WalletTicketSerializer
    lookup_field = "code"
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        return Ticket.objects.select_related(*TICKET_RELATED).filter(holder=self.request.user)


class TicketTransferView(APIView):
    """Send a ticket to a friend by phone or email. Your copy stops working."""

    @extend_schema(request=TransferSerializer, responses=WalletTicketSerializer)
    def post(self, request, code):
        ticket = get_object_or_404(Ticket, code=code.upper(), holder=request.user)
        ser = TransferSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            ticket = transfer_ticket(
                ticket, by_user=request.user, to=ser.validated_data["to"], to_name=ser.validated_data["name"]
            )
        except TransferError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"detail": "Ticket sent.", "sent_to": ser.validated_data["to"].masked})


class WalletTicketPdfView(APIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, code):
        ticket = get_object_or_404(Ticket.objects.select_related(*TICKET_RELATED), code=code.upper(),
                                   holder=request.user)
        return _pdf_response([ticket], f"ticket-{ticket.code}.pdf")


# --------------------------------------------------------------------------
# Private ticket pages (links sent by SMS/email; no login, no app needed)
# --------------------------------------------------------------------------
def _pdf_response(tickets, filename) -> HttpResponse:
    resp = HttpResponse(tickets_pdf(tickets), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


def _check(token: str, expected: str):
    if not hmac.compare_digest(token, expected):
        raise Http404


def _order_for_page(reference, token) -> Order:
    order = get_object_or_404(Order.objects.select_related("event__venue"), reference=reference.upper())
    _check(token, order.access_token)
    return order


def _page_context(tickets, event, **extra):
    return {
        "event": event, "when": format_when(event), "where": format_where(event),
        "tickets": [
            {"t": t, "qr": qr_svg(t.qr_payload) if (t.qr_active and not extra.get("hide_qr", {}).get(t.pk)) else None}
            for t in tickets
        ],
        "platform_name": settings.PLATFORM_NAME,
        **extra,
    }


def order_tickets_page(request, reference, token):
    order = _order_for_page(reference, token)
    if order.status != OrderStatus.PAID:
        return render(request, "tickets/not_ready.html", {"order": order}, status=404)
    tickets = list(order.tickets.select_related("ticket_type", "event"))
    # Tickets sent to someone else no longer show a QR to the buyer.
    hide = {t.pk: True for t in tickets if t.transferred_at}
    ctx = _page_context(tickets, order.event, order=order, hide_qr=hide,
                        pdf_url=f"{order.tickets_url}pdf/")
    return render(request, "tickets/tickets_page.html", ctx)


def order_tickets_pdf(request, reference, token):
    order = _order_for_page(reference, token)
    if order.status != OrderStatus.PAID:
        raise Http404
    tickets = [t for t in order.tickets.select_related(*TICKET_RELATED) if not t.transferred_at]
    if not tickets:
        raise Http404
    return _pdf_response(tickets, f"tickets-{order.reference}.pdf")


def single_ticket_page(request, code, token):
    ticket = get_object_or_404(Ticket.objects.select_related(*TICKET_RELATED), code=code.upper())
    _check(token, ticket.access_token)
    ctx = _page_context([ticket], ticket.event, pdf_url=f"{ticket.page_url}pdf/")
    return render(request, "tickets/tickets_page.html", ctx)


def single_ticket_pdf(request, code, token):
    ticket = get_object_or_404(Ticket.objects.select_related(*TICKET_RELATED), code=code.upper())
    _check(token, ticket.access_token)
    return _pdf_response([ticket], f"ticket-{ticket.code}.pdf")
