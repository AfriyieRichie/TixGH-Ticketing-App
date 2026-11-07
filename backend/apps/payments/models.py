import secrets

from django.db import models

from apps.orders.models import Order


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
