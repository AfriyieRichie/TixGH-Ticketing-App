from django.db import models

from apps.orders.models import Order


class DeliveryStatus(models.TextChoices):
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class Delivery(models.Model):
    """
    A log of every SMS/email sent to buyers, so support can answer
    "I didn't get my ticket" and resend if needed.
    """

    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries")
    kind = models.CharField(max_length=30, help_text="order_confirmation, transfer, reminder, cancellation, ...")
    channel = models.CharField(max_length=10, help_text="sms | email")
    to = models.CharField(max_length=254)
    status = models.CharField(max_length=10, choices=DeliveryStatus.choices)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "deliveries"

    def __str__(self):
        return f"{self.kind} via {self.channel} to {self.to} ({self.status})"
