import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.events.models import Event, PromoCode, TicketType

# No 0/O/1/I/L so codes are easy to read out at the gate or over the phone.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def random_code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def _order_reference() -> str:
    return "TX" + random_code(8)


def _access_token() -> str:
    return secrets.token_urlsafe(24)


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Awaiting payment"
    PAID = "paid", "Paid"
    EXPIRED = "expired", "Expired (not paid in time)"
    FAILED = "failed", "Payment failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
    NEEDS_REVIEW = "needs_review", "Paid but needs staff review"


class Order(models.Model):
    """A buyer's purchase of one or more tickets for a single event."""

    reference = models.CharField(max_length=12, unique=True, default=_order_reference, editable=False)
    access_token = models.CharField(
        max_length=40, default=_access_token, editable=False,
        help_text="Lets a guest buyer view their order without an account",
    )
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="orders")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    buyer_name = models.CharField(max_length=150)
    buyer_email = models.EmailField(blank=True)
    buyer_phone = models.CharField(max_length=20, blank=True, help_text="E.164")

    status = models.CharField(max_length=15, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    promo_code = models.ForeignKey(PromoCode, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    fee_bearer = models.CharField(max_length=12)

    # All amounts in GHS.
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, help_text="Face value after discount")
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    fee_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, help_text="What the buyer pays")
    organizer_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Platform's share before the gateway's charge"
    )
    currency = models.CharField(max_length=3, default="GHS")

    expires_at = models.DateTimeField(help_text="Tickets are held until this time")
    paid_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["event", "status"]),
            models.Index(fields=["buyer_phone"]),
            models.Index(fields=["buyer_email"]),
        ]

    def __str__(self):
        return f"{self.reference} ({self.get_status_display()})"

    @property
    def is_free(self) -> bool:
        return self.total == 0

    @property
    def is_hold_active(self) -> bool:
        return self.status == OrderStatus.PENDING and timezone.now() < self.expires_at

    @property
    def ticket_count(self) -> int:
        return sum(i.quantity for i in self.items.all())

    @property
    def tickets_url(self) -> str:
        """Private page with all of this order's tickets (sent by SMS/email)."""
        return f"{settings.BACKEND_URL}/t/{self.reference}/{self.access_token}/"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveSmallIntegerField()
    # Per-ticket amounts captured at purchase time (prices may change later).
    unit_list_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Before discount")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="After discount")
    unit_fee = models.DecimalField(max_digits=10, decimal_places=2)
    unit_buyer_pays = models.DecimalField(max_digits=10, decimal_places=2)
    unit_organizer_receives = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.ticket_type.name}"

    @property
    def line_total(self) -> Decimal:
        return self.unit_buyer_pays * self.quantity


def _ticket_code() -> str:
    return random_code(10)


class TicketStatus(models.TextChoices):
    VALID = "valid", "Valid"
    CHECKED_IN = "checked_in", "Checked in"
    VOID = "void", "Void (refunded or cancelled)"


class Ticket(models.Model):
    """One admission (or one table/group ticket). Issued when an order is paid."""

    code = models.CharField(max_length=12, unique=True, default=_ticket_code, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tickets")
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="tickets")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="tickets")
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name="tickets")
    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets"
    )
    attendee_name = models.CharField(max_length=150, blank=True)
    # Who the ticket was sent to when there's no account yet (e.g. after a transfer).
    attendee_phone = models.CharField(max_length=20, blank=True)
    attendee_email = models.EmailField(blank=True)
    access_token = models.CharField(
        max_length=40, default=_access_token, editable=False, help_text="For the ticket's private link"
    )
    status = models.CharField(max_length=12, choices=TicketStatus.choices, default=TicketStatus.VALID)
    checked_in_at = models.DateTimeField(null=True, blank=True, help_text="First entry")
    # Gate state. A ticket can admit several people (e.g. a table for 8).
    admitted = models.PositiveSmallIntegerField(default=0, help_text="People who have entered at least once")
    inside = models.PositiveSmallIntegerField(default=0, help_text="People currently inside")
    reentries = models.PositiveSmallIntegerField(default=0)
    transferred_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when sent to someone else; the buyer's order page then hides its QR"
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    # Lets gate scanners download only what changed since their last sync.
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["issued_at", "id"]
        indexes = [models.Index(fields=["event", "status"])]

    def __str__(self):
        return f"{self.code} ({self.ticket_type.name})"

    @property
    def qr_active(self) -> bool:
        """Whether the QR should be shown/usable: unused, or used at an event that allows re-entry."""
        if self.status == TicketStatus.VALID:
            return True
        return self.status == TicketStatus.CHECKED_IN and self.event.reentry_allowed

    @property
    def qr_payload(self) -> str:
        from apps.tickets.signing import qr_payload

        return qr_payload(self)

    @property
    def page_url(self) -> str:
        return f"{settings.BACKEND_URL}/t/ticket/{self.code}/{self.access_token}/"
