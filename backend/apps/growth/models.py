from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.events.models import Event
from apps.organizations.models import Organization


class Follow(models.Model):
    """A user following an organizer, to hear about their new events."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follows")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="followers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="unique_follow")]

    def __str__(self):
        return f"{self.user} follows {self.organization}"


class TrackingLink(TimeStampedModel):
    """A promoter/influencer link: /e/<event>?ref=<code>. Sales are attributed to it."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="tracking_links")
    code = models.SlugField(max_length=40, help_text="Appears in the link, e.g. KOFI or instagram")
    label = models.CharField(max_length=100, help_text="Who or where, e.g. 'Kofi (influencer)'")
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Promoter's share of ticket revenue from this link (for your records)",
    )
    clicks = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "code"], name="unique_ref_per_event")]

    def __str__(self):
        return f"{self.code} ({self.event.title})"


class CampaignAudience(models.TextChoices):
    ALL = "all", "Followers and past attendees who opted in"
    FOLLOWERS = "followers", "Followers only"
    PAST_ATTENDEES = "past_attendees", "Past attendees who opted in"


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"


class Campaign(TimeStampedModel):
    """An email from an organizer to their audience (e.g. 'Our next show is here')."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="campaigns")
    subject = models.CharField(max_length=150)
    body = models.TextField(help_text="Plain text. Blank lines start new paragraphs.")
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns",
                              help_text="Event to promote: adds a 'Get tickets' button")
    audience = models.CharField(max_length=20, choices=CampaignAudience.choices, default=CampaignAudience.ALL)
    status = models.CharField(max_length=10, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    automatic = models.BooleanField(default=False, help_text="Sent by the system (e.g. new event to followers)")
    recipients_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    queued_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class RecipientStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped (unsubscribed)"


class CampaignRecipient(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    email = models.EmailField()
    name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=10, choices=RecipientStatus.choices, default=RecipientStatus.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campaign", "email"], name="unique_campaign_recipient")]
        indexes = [models.Index(fields=["status", "campaign"])]


class Unsubscribe(models.Model):
    """Someone who asked not to receive an organizer's marketing emails."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="unsubscribes")
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "email"], name="unique_unsubscribe")]


class Review(TimeStampedModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, max_length=2000)
    organizer_reply = models.TextField(blank=True, max_length=2000)
    replied_at = models.DateTimeField(null=True, blank=True)
    is_hidden = models.BooleanField(default=False, help_text="Hidden by platform staff (abuse)")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="one_review_per_event")]

    def __str__(self):
        return f"{self.rating}★ {self.event.title}"
