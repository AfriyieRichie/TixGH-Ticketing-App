import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify

from apps.core.constants import GhanaRegion
from apps.core.models import FeeBearer, TimeStampedModel
from apps.organizations.models import Organization


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True)
    icon = models.CharField(max_length=40, blank=True, help_text="Icon name used by the apps")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Venue(TimeStampedModel):
    """A place events happen. Owned by an organizer so they can reuse it."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="venues")
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80)
    region = models.CharField(max_length=20, choices=GhanaRegion.choices)
    digital_address = models.CharField(
        max_length=20, blank=True, help_text="GhanaPostGPS address, e.g. GA-123-4567"
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    directions = models.TextField(blank=True, help_text="Landmarks, parking, entrance tips")
    capacity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.city}"


class EventStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    CANCELLED = "cancelled", "Cancelled"


class EventFormat(models.TextChoices):
    IN_PERSON = "in_person", "In person"
    ONLINE = "online", "Online"
    HYBRID = "hybrid", "In person and online"


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public (listed in search)"
    UNLISTED = "unlisted", "Unlisted (only people with the link)"


class RefundPolicy(models.TextChoices):
    NO_REFUNDS = "no_refunds", "No refunds"
    UP_TO_1_DAY = "1_day", "Refunds up to 1 day before the event"
    UP_TO_7_DAYS = "7_days", "Refunds up to 7 days before the event"
    UP_TO_30_DAYS = "30_days", "Refunds up to 30 days before the event"


def _slug_suffix() -> str:
    return secrets.token_hex(3)


class EventQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=EventStatus.PUBLISHED, organization__is_active=True)

    def upcoming(self):
        return self.filter(end_at__gte=timezone.now())

    def listed(self):
        """What appears in public discovery."""
        return self.published().upcoming().filter(visibility=Visibility.PUBLIC)


class Event(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="events")
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, editable=False)
    summary = models.CharField(max_length=280, blank=True, help_text="One or two lines shown on event cards")
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    cover_image = models.ImageField(upload_to="event_covers/", blank=True)

    format = models.CharField(max_length=10, choices=EventFormat.choices, default=EventFormat.IN_PERSON)
    venue = models.ForeignKey(Venue, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    online_url = models.URLField(blank=True, help_text="Only shown to ticket holders")

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    status = models.CharField(max_length=10, choices=EventStatus.choices, default=EventStatus.DRAFT)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC)
    age_restriction = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(21)], help_text="Minimum age; 0 = all ages"
    )
    max_tickets_per_order = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    fee_bearer = models.CharField(
        max_length=12, choices=FeeBearer.choices, blank=True,
        help_text="Blank = organizer's default, then platform default",
    )
    allow_transfers = models.BooleanField(default=True, help_text="Ticket holders may send tickets to someone else")
    refund_policy = models.CharField(max_length=10, choices=RefundPolicy.choices, default=RefundPolicy.NO_REFUNDS)
    refund_policy_details = models.TextField(blank=True)

    is_featured = models.BooleanField(default=False, help_text="Shown on the homepage (paid add-on)")
    published_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["start_at"]
        indexes = [
            models.Index(fields=["status", "visibility", "start_at"]),
            models.Index(fields=["organization", "status"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=F("start_at")), name="event_ends_after_start")
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:150] or "event"
            self.slug = f"{base}-{_slug_suffix()}"
            while Event.objects.filter(slug=self.slug).exists():
                self.slug = f"{base}-{_slug_suffix()}"
        super().save(*args, **kwargs)

    # ---- Derived state -------------------------------------------------
    @property
    def has_ended(self) -> bool:
        return timezone.now() >= self.end_at

    @property
    def is_live(self) -> bool:
        return self.status == EventStatus.PUBLISHED and not self.has_ended

    @property
    def effective_fee_bearer(self) -> str:
        from apps.core.models import PlatformSettings

        return self.fee_bearer or self.organization.fee_bearer or PlatformSettings.load().default_fee_bearer

    @property
    def tickets_sold(self) -> int:
        return sum(t.quantity_sold for t in self.ticket_types.all())

    def publish_problems(self) -> list[str]:
        """Reasons this event cannot be published yet (empty list = ready)."""
        problems = []
        if not self.organization.is_active:
            problems.append("Your organizer account is inactive.")
        if self.end_at <= timezone.now():
            problems.append("The event end time is in the past.")
        if self.format in (EventFormat.IN_PERSON, EventFormat.HYBRID) and not self.venue_id:
            problems.append("Add a venue.")
        if self.format in (EventFormat.ONLINE, EventFormat.HYBRID) and not self.online_url:
            problems.append("Add the online event link.")
        types = [t for t in self.ticket_types.all() if t.is_active]
        if not types:
            problems.append("Add at least one ticket type.")
        if any(t.price > 0 for t in types) and not self.organization.payout_accounts.exists():
            problems.append("Add a payout account before selling paid tickets.")
        return problems


class TicketVisibility(models.TextChoices):
    VISIBLE = "visible", "Visible"
    HIDDEN = "hidden", "Hidden (unlocked by an access code)"


class TicketType(TimeStampedModel):
    """e.g. Early Bird, Regular, VIP, Table for 10."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="ticket_types")
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=500, blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))], help_text="GHS. 0 = free",
    )
    quantity = models.PositiveIntegerField(help_text="Total tickets available")
    quantity_sold = models.PositiveIntegerField(default=0, editable=False)
    admits = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="People admitted per ticket, e.g. 10 for a table",
    )
    min_per_order = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    max_per_order = models.PositiveSmallIntegerField(default=10, validators=[MinValueValidator(1)])
    sales_start_at = models.DateTimeField(null=True, blank=True, help_text="Blank = on sale when published")
    sales_end_at = models.DateTimeField(null=True, blank=True, help_text="Blank = until the event ends")
    visibility = models.CharField(max_length=10, choices=TicketVisibility.choices, default=TicketVisibility.VISIBLE)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "price", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity_sold__lte=F("quantity")), name="ticket_not_oversold"),
            models.CheckConstraint(condition=Q(max_per_order__gte=F("min_per_order")), name="ticket_min_lte_max"),
        ]

    def __str__(self):
        return f"{self.event.title}: {self.name}"

    def clean(self):
        if self.sales_start_at and self.sales_end_at and self.sales_end_at <= self.sales_start_at:
            raise ValidationError({"sales_end_at": "Sales must end after they start."})

    @property
    def is_free(self) -> bool:
        return self.price == 0

    @property
    def quantity_available(self) -> int:
        return max(self.quantity - self.quantity_sold, 0)

    @property
    def effective_sales_end(self):
        return self.sales_end_at or self.event.end_at

    @property
    def sale_status(self) -> str:
        """on_sale | scheduled | ended | sold_out | unavailable"""
        now = timezone.now()
        if not self.is_active or self.event.status != EventStatus.PUBLISHED:
            return "unavailable"
        if now >= self.effective_sales_end:
            return "ended"
        if self.sales_start_at and now < self.sales_start_at:
            return "scheduled"
        if self.quantity_available == 0:
            return "sold_out"
        return "on_sale"


class DiscountType(models.TextChoices):
    PERCENT = "percent", "Percentage off"
    FIXED = "fixed", "Fixed amount off (GHS)"
    NONE = "none", "No discount (access code only)"


class PromoCode(TimeStampedModel):
    """A discount code and/or an access code that unlocks hidden ticket types."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="promo_codes")
    code = models.CharField(max_length=30)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(0)]
    )
    ticket_types = models.ManyToManyField(
        TicketType, blank=True, related_name="promo_codes", help_text="Blank = applies to all ticket types"
    )
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Blank = unlimited")
    times_used = models.PositiveIntegerField(default=0, editable=False)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "code"], name="unique_promo_code_per_event")
        ]

    def __str__(self):
        return f"{self.code} ({self.event.title})"

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def problem(self) -> str | None:
        """Why the code can't be used right now, or None if it's usable."""
        now = timezone.now()
        if not self.is_active:
            return "This code is no longer active."
        if self.valid_from and now < self.valid_from:
            return "This code is not active yet."
        if self.valid_until and now >= self.valid_until:
            return "This code has expired."
        if self.max_uses is not None and self.times_used >= self.max_uses:
            return "This code has been fully used."
        return None

    def applies_to(self, ticket_type: TicketType) -> bool:
        ids = [t.pk for t in self.ticket_types.all()]
        return not ids or ticket_type.pk in ids

    def discounted_price(self, price: Decimal) -> Decimal:
        if self.discount_type == DiscountType.PERCENT:
            off = price * min(self.amount, Decimal(100)) / Decimal(100)
        elif self.discount_type == DiscountType.FIXED:
            off = self.amount
        else:
            off = Decimal(0)
        return max(price - off, Decimal(0)).quantize(Decimal("0.01"))
