import re
from decimal import Decimal

from rest_framework import serializers

from apps.core.models import PlatformSettings

from .models import (
    Category,
    DiscountType,
    Event,
    EventStatus,
    PromoCode,
    TicketType,
    TicketVisibility,
    Venue,
)
from .pricing import price_breakdown

MAX_COVER_BYTES = 5 * 1024 * 1024
LOW_STOCK_THRESHOLD = 20


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["name", "slug", "icon"]


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = [
            "id", "name", "address", "city", "region", "digital_address",
            "latitude", "longitude", "directions", "capacity",
        ]


class PublicVenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["name", "address", "city", "region", "digital_address", "latitude", "longitude", "directions"]


# --------------------------------------------------------------------------
# Organizer-facing
# --------------------------------------------------------------------------
class TicketTypeSerializer(serializers.ModelSerializer):
    quantity_available = serializers.IntegerField(read_only=True)
    sale_status = serializers.CharField(read_only=True)
    pricing = serializers.SerializerMethodField()

    class Meta:
        model = TicketType
        fields = [
            "id", "name", "description", "price", "quantity", "quantity_sold", "quantity_available",
            "admits", "min_per_order", "max_per_order", "sales_start_at", "sales_end_at",
            "visibility", "sort_order", "is_active", "sale_status", "pricing",
        ]
        read_only_fields = ["quantity_sold"]

    def get_pricing(self, obj) -> dict:
        return price_breakdown(obj.event, obj.price).as_dict()

    def validate(self, attrs):
        inst = self.instance
        get = lambda f: attrs.get(f, getattr(inst, f, None))  # noqa: E731
        event = self.context["event"]
        if inst and get("quantity") < inst.quantity_sold:
            raise serializers.ValidationError(
                {"quantity": f"{inst.quantity_sold} tickets are already sold; quantity can't be lower."}
            )
        if (get("min_per_order") or 1) > (get("max_per_order") or 10):
            raise serializers.ValidationError({"max_per_order": "Must be at least the minimum per order."})
        start, end = get("sales_start_at"), get("sales_end_at")
        if start and end and end <= start:
            raise serializers.ValidationError({"sales_end_at": "Sales must end after they start."})
        if end and end > event.end_at:
            raise serializers.ValidationError({"sales_end_at": "Sales can't continue after the event ends."})
        if start and start >= event.end_at:
            raise serializers.ValidationError({"sales_start_at": "Sales must start before the event ends."})
        if inst and inst.quantity_sold and "price" in attrs and attrs["price"] == 0 and inst.price > 0:
            raise serializers.ValidationError({"price": "Can't make a ticket free after paid sales."})
        return attrs


class PromoCodeSerializer(serializers.ModelSerializer):
    ticket_types = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=TicketType.objects.none()
    )

    class Meta:
        model = PromoCode
        fields = [
            "id", "code", "discount_type", "amount", "ticket_types", "max_uses", "times_used",
            "valid_from", "valid_until", "is_active", "created_at",
        ]
        read_only_fields = ["times_used", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        event = self.context.get("event")
        if event is not None:
            self.fields["ticket_types"].child_relation.queryset = event.ticket_types.all()

    def validate_code(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{3,30}", value):
            raise serializers.ValidationError("Use 3-30 letters, numbers, - or _.")
        qs = self.context["event"].promo_codes.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This event already has that code.")
        return value

    def validate(self, attrs):
        get = lambda f: attrs.get(f, getattr(self.instance, f, None))  # noqa: E731
        kind = get("discount_type") or DiscountType.PERCENT  # model default when omitted
        amount = get("amount") or Decimal(0)
        if kind == DiscountType.PERCENT and not (0 < amount <= 100):
            raise serializers.ValidationError({"amount": "Percentage must be between 0 and 100."})
        if kind == DiscountType.FIXED and amount <= 0:
            raise serializers.ValidationError({"amount": "Enter the amount off in GHS."})
        if kind == DiscountType.NONE:
            attrs["amount"] = Decimal(0)
        vf, vu = get("valid_from"), get("valid_until")
        if vf and vu and vu <= vf:
            raise serializers.ValidationError({"valid_until": "Must be after the start date."})
        return attrs


class EventSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(
        slug_field="slug", queryset=Category.objects.filter(is_active=True), required=False, allow_null=True
    )
    venue = serializers.PrimaryKeyRelatedField(queryset=Venue.objects.none(), required=False, allow_null=True)
    venue_detail = VenueSerializer(source="venue", read_only=True)
    ticket_types = TicketTypeSerializer(many=True, read_only=True)
    effective_fee_bearer = serializers.CharField(read_only=True)
    tickets_sold = serializers.IntegerField(read_only=True)
    has_ended = serializers.BooleanField(read_only=True)
    publish_problems = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id", "slug", "title", "summary", "description", "category", "cover_image",
            "format", "venue", "venue_detail", "online_url", "start_at", "end_at",
            "status", "visibility", "age_restriction", "max_tickets_per_order",
            "fee_bearer", "effective_fee_bearer", "allow_transfers", "reentry_allowed", "max_reentries",
            "reentry_cutoff_at", "refund_policy", "refund_policy_details",
            "is_featured", "published_at", "cancelled_at", "cancellation_reason",
            "ticket_types", "tickets_sold", "has_ended", "publish_problems",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "slug", "status", "is_featured", "published_at", "cancelled_at", "cancellation_reason",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("organization")
        if org is not None:
            self.fields["venue"].queryset = org.venues.all()

    def get_publish_problems(self, obj) -> list[str]:
        return obj.publish_problems() if obj.status == EventStatus.DRAFT else []

    def validate_cover_image(self, value):
        if value and value.size > MAX_COVER_BYTES:
            raise serializers.ValidationError("Cover image must be 5 MB or smaller.")
        return value

    def validate(self, attrs):
        get = lambda f: attrs.get(f, getattr(self.instance, f, None))  # noqa: E731
        start, end = get("start_at"), get("end_at")
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "The event must end after it starts."})
        if self.instance and self.instance.status == EventStatus.CANCELLED:
            raise serializers.ValidationError("Cancelled events can't be edited.")
        return attrs


class CancelEventSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------
class PublicOrganizerSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()
    logo = serializers.ImageField()
    is_verified = serializers.BooleanField()


def _visible_types(event, unlocked_ids=()):
    return [
        t for t in event.ticket_types.all()
        if t.is_active and (t.visibility == TicketVisibility.VISIBLE or t.pk in unlocked_ids)
    ]


class PublicTicketTypeSerializer(serializers.ModelSerializer):
    sale_status = serializers.CharField(read_only=True)
    pricing = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField(help_text="Only shown when few tickets are left")

    class Meta:
        model = TicketType
        fields = [
            "id", "name", "description", "admits", "min_per_order", "max_per_order",
            "sales_start_at", "sales_end_at", "sale_status", "pricing", "remaining",
        ]

    def get_pricing(self, obj) -> dict:
        return price_breakdown(obj.event, obj.price, self.context.get("platform")).as_dict()

    def get_remaining(self, obj) -> int | None:
        left = obj.quantity_available
        return left if left <= LOW_STOCK_THRESHOLD else None


class PublicEventListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    venue = serializers.SerializerMethodField()
    organizer = PublicOrganizerSerializer(source="organization", read_only=True)
    price_from = serializers.SerializerMethodField(help_text="Lowest price a buyer pays (GHS), incl. fees")
    is_free = serializers.SerializerMethodField()
    sold_out = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "slug", "title", "summary", "cover_image", "category", "format", "start_at", "end_at",
            "venue", "organizer", "price_from", "is_free", "sold_out", "is_featured", "status",
        ]

    def get_venue(self, obj) -> dict | None:
        v = obj.venue
        return {"name": v.name, "city": v.city, "region": v.region} if v else None

    def _types(self, obj):
        return _visible_types(obj)

    def get_price_from(self, obj) -> str | None:
        platform = self.context.get("platform")
        prices = [price_breakdown(obj, t.price, platform).buyer_pays for t in self._types(obj)]
        return str(min(prices)) if prices else None

    def get_is_free(self, obj) -> bool:
        types = self._types(obj)
        return bool(types) and all(t.price == 0 for t in types)

    def get_sold_out(self, obj) -> bool:
        types = self._types(obj)
        return bool(types) and all(t.quantity_available == 0 for t in types)


class PublicEventDetailSerializer(PublicEventListSerializer):
    venue = PublicVenueSerializer(read_only=True)
    ticket_types = serializers.SerializerMethodField()
    has_ended = serializers.BooleanField(read_only=True)
    organizer_description = serializers.CharField(source="organization.description", read_only=True)

    class Meta(PublicEventListSerializer.Meta):
        fields = PublicEventListSerializer.Meta.fields + [
            "description", "ticket_types", "age_restriction", "max_tickets_per_order", "allow_transfers",
            "reentry_allowed", "max_reentries", "reentry_cutoff_at",
            "refund_policy", "refund_policy_details", "has_ended", "cancellation_reason",
            "organizer_description",
        ]

    def get_ticket_types(self, obj) -> list[dict]:
        return PublicTicketTypeSerializer(_visible_types(obj), many=True, context=self.context).data


class PromoCheckSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)


def platform_context() -> dict:
    """Load platform settings once per request instead of once per ticket."""
    return {"platform": PlatformSettings.load()}
