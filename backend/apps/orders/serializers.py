from django.utils import timezone
from rest_framework import serializers

from apps.core.phone import InvalidPhoneNumber, normalize_phone
from apps.notifications.services import whatsapp_share_url

from .models import Order, OrderItem, OrderStatus, Ticket, TicketStatus


class CheckoutItemSerializer(serializers.Serializer):
    ticket_type = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=0, max_value=100)


class BuyerSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, help_text="Tickets are sent here by SMS")

    def validate_phone(self, value):
        if not value:
            return ""
        try:
            return normalize_phone(value)
        except InvalidPhoneNumber as exc:
            raise serializers.ValidationError(str(exc))


class CheckoutSerializer(serializers.Serializer):
    event = serializers.SlugField(help_text="Event slug")
    items = CheckoutItemSerializer(many=True, allow_empty=False)
    promo_code = serializers.CharField(max_length=30, required=False, allow_blank=True)
    buyer = BuyerSerializer(required=False)

    def validate(self, attrs):
        """Fill buyer details from the signed-in account; require a way to deliver tickets."""
        user = self.context["request"].user
        buyer = dict(attrs.get("buyer") or {})
        if user.is_authenticated:
            buyer["full_name"] = buyer.get("full_name") or user.full_name
            buyer["email"] = buyer.get("email") or user.email or ""
            buyer["phone"] = buyer.get("phone") or user.phone or ""
        if not buyer.get("full_name", "").strip():
            raise serializers.ValidationError({"buyer": {"full_name": ["Enter your name."]}})
        if not buyer.get("email") and not buyer.get("phone"):
            raise serializers.ValidationError(
                {"buyer": {"phone": ["Enter a phone number or email so we can send your tickets."]}}
            )
        buyer["email"] = (buyer.get("email") or "").lower()
        attrs["buyer"] = buyer
        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "ticket_type", "ticket_type_name", "quantity", "unit_list_price", "unit_price",
            "unit_fee", "unit_buyer_pays", "line_total",
        ]


class TicketSerializer(serializers.ModelSerializer):
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)
    admits = serializers.IntegerField(source="ticket_type.admits", read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "code", "qr_payload", "ticket_type_name", "admits", "attendee_name", "status",
            "checked_in_at", "transferred",
        ]

    qr_payload = serializers.SerializerMethodField()
    transferred = serializers.SerializerMethodField(help_text="Sent to someone else; the QR now belongs to them")

    def get_qr_payload(self, obj) -> str | None:
        return obj.qr_payload if obj.qr_active and not obj.transferred_at else None

    def get_transferred(self, obj) -> bool:
        return obj.transferred_at is not None


class OrderEventSerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    cover_image = serializers.ImageField()
    venue_name = serializers.CharField(source="venue.name", default=None)
    venue_city = serializers.CharField(source="venue.city", default=None)


class OrderSerializer(serializers.ModelSerializer):
    event = OrderEventSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    tickets = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    promo_code = serializers.CharField(source="promo_code.code", default=None, read_only=True)
    seconds_left = serializers.SerializerMethodField(help_text="Time left to pay before tickets are released")
    links = serializers.SerializerMethodField(help_text="Ticket page, PDF and WhatsApp share links (paid orders)")

    class Meta:
        model = Order
        fields = [
            "reference", "access_token", "status", "event", "buyer_name", "buyer_email", "buyer_phone",
            "items", "promo_code", "subtotal", "discount_total", "fee_total", "total", "currency",
            "fee_bearer", "expires_at", "seconds_left", "paid_at", "created_at", "payment", "tickets", "links",
        ]

    def get_tickets(self, obj) -> list[dict]:
        if obj.status != OrderStatus.PAID:
            return []
        return TicketSerializer(obj.tickets.select_related("ticket_type"), many=True).data

    def get_payment(self, obj) -> dict | None:
        p = obj.payments.first()  # newest first
        if p is None:
            return None
        return {
            "reference": p.reference, "status": p.status, "gateway": p.gateway,
            "authorization_url": p.authorization_url if obj.status == OrderStatus.PENDING else "",
            "access_code": p.access_code if obj.status == OrderStatus.PENDING else "",
            "channel": p.channel,
        }

    def get_seconds_left(self, obj) -> int:
        if obj.status != OrderStatus.PENDING:
            return 0
        return max(int((obj.expires_at - timezone.now()).total_seconds()), 0)

    def get_links(self, obj) -> dict | None:
        if obj.status != OrderStatus.PAID:
            return None
        return {
            "tickets_page": obj.tickets_url,
            "pdf": f"{obj.tickets_url}pdf/",
            "whatsapp_share": whatsapp_share_url(obj),
        }
