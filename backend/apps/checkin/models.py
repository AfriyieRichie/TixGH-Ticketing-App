from django.conf import settings
from django.db import models

from apps.events.models import Event
from apps.orders.models import Ticket


class ScanResult(models.TextChoices):
    OK = "ok", "Admitted"
    DUPLICATE = "duplicate", "Already checked in"
    INVALID = "invalid", "Not a valid ticket"
    TRANSFERRED = "transferred", "Old code from a transferred ticket"
    VOID = "void", "Ticket voided or refunded"
    WRONG_EVENT = "wrong_event", "Ticket is for another event"
    EVENT_CANCELLED = "event_cancelled", "Event cancelled"
    REENTRY = "reentry", "Re-entry"
    NO_REENTRY = "no_reentry", "Re-entry not allowed"
    EXIT = "exit", "Exit"
    NOT_INSIDE = "not_inside", "Not inside"


class Direction(models.TextChoices):
    IN = "in", "Entry"
    OUT = "out", "Exit"


class CheckIn(models.Model):
    """Every scan at the gate, including rejected ones (audit trail and fraud alerts)."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="scans")
    ticket = models.ForeignKey(Ticket, null=True, blank=True, on_delete=models.SET_NULL, related_name="scans")
    raw = models.CharField(max_length=120, help_text="What was scanned or typed")
    result = models.CharField(max_length=20, choices=ScanResult.choices)
    direction = models.CharField(max_length=3, choices=Direction.choices, default=Direction.IN)
    people = models.PositiveSmallIntegerField(default=0, help_text="People moved through the gate by this scan")
    # What this scan changed on the ticket, so it can be undone exactly.
    delta_admitted = models.SmallIntegerField(default=0)
    delta_inside = models.SmallIntegerField(default=0)
    delta_reentries = models.SmallIntegerField(default=0)
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    gate = models.CharField(max_length=40, blank=True)
    device_id = models.CharField(max_length=64, blank=True)
    scanned_at = models.DateTimeField(help_text="When the scan happened on the device (may be offline)")
    received_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-scanned_at"]
        indexes = [models.Index(fields=["event", "result"])]

    def __str__(self):
        return f"{self.raw} → {self.result}"
