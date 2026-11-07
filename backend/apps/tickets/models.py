from django.conf import settings
from django.db import models

from apps.orders.models import Ticket


class TicketTransfer(models.Model):
    """Audit trail of a ticket being sent from one person to another."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="transfers")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_name = models.CharField(max_length=150)
    to_contact = models.CharField(max_length=254, help_text="Normalized phone or email")
    old_code = models.CharField(max_length=12)
    new_code = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.old_code} -> {self.new_code} ({self.to_contact})"
