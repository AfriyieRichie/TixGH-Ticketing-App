import secrets

from django.conf import settings
from django.db import models

from apps.orders.models import Order, Ticket


def _payment_reference() -> str:
    return "PAY-" + secrets.token_hex(8).upper()


class PaymentStatus(models.TextChoices):
    INITIALIZED = "initialized", "Waiting for buyer"
    SUCCESS = "success", "Successful"
    FAILED = "failed", "Failed"
    ABANDONED = "abandoned", "Abandoned"


class Payment(models.Model):
    """One attempt to pay for an order through a payment gateway."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=20)
    reference = models.CharField(max_length=40, unique=True, default=_payment_reference, editable=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="GHS")
    status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.INITIALIZED)
    channel = models.CharField(max_length=30, blank=True, help_text="mobile_money, card, ...")
    authorization_url = models.URLField(max_length=500, blank=True)
    access_code = models.CharField(max_length=100, blank=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.amount} {self.currency} ({self.status})"


class RefundKind(models.TextChoices):
    CANCELLATION = "cancellation", "Event cancelled (full refund incl. booking fee)"
    ORGANIZER = "organizer", "Issued by organizer"
    BUYER_REQUEST = "buyer_request", "Requested by buyer (within refund policy)"


class RefundStatus(models.TextChoices):
    PENDING = "pending", "Waiting to be sent"
    PROCESSING = "processing", "Sent to payment provider"
    PROCESSED = "processed", "Refunded"
    FAILED = "failed", "Failed (staff action needed)"


class Refund(models.Model):
    """Money returned to a buyer for some or all tickets in an order."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="refunds")
    tickets = models.ManyToManyField(Ticket, related_name="refunds")
    kind = models.CharField(max_length=15, choices=RefundKind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Returned to the buyer (GHS)")
    organizer_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="Taken back from the organizer's earnings")
    platform_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                          help_text="Booking fees returned by the platform")
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    gateway_reference = models.CharField(max_length=60, blank=True)
    error = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {self.amount} for {self.order.reference} ({self.status})"
