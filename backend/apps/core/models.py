from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class FeeBearer(models.TextChoices):
    BUYER = "buyer", "Ticket buyer pays fees"
    ORGANIZER = "organizer", "Organizer absorbs fees"


class PlatformSettings(models.Model):
    """
    Singleton holding business settings that staff can change from the admin
    without a code deploy (fees, support contacts, ...).
    """

    CACHE_KEY = "platform_settings"

    # Ticket fee charged on every *paid* ticket (free tickets are never charged).
    # The gateway (Paystack) charge is paid out of this fee by the platform.
    fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Percentage of the ticket price, e.g. 5.00 = 5%.",
    )
    fee_flat = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=[MinValueValidator(0)],
        help_text="Flat amount (GHS) added per paid ticket.",
    )
    fee_cap = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Optional maximum fee per ticket (GHS). Leave blank for no cap.",
    )
    default_fee_bearer = models.CharField(
        max_length=12, choices=FeeBearer.choices, default=FeeBearer.BUYER
    )
    currency = models.CharField(max_length=3, default="GHS", editable=False)

    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=20, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Platform settings"
        verbose_name_plural = "Platform settings"

    def __str__(self):
        return "Platform settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    def delete(self, *args, **kwargs):
        pass  # The singleton cannot be deleted.

    @classmethod
    def load(cls) -> "PlatformSettings":
        obj = cache.get(cls.CACHE_KEY)
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, obj, 300)
        return obj

    def ticket_fee(self, price: Decimal, percent: Decimal | None = None, flat: Decimal | None = None) -> Decimal:
        """
        Platform fee for a single ticket at `price` GHS. `percent`/`flat`
        override the platform defaults (e.g. an organizer's negotiated rate).
        """
        price = Decimal(price)
        if price <= 0:
            return Decimal("0.00")
        percent = self.fee_percent if percent is None else percent
        flat = self.fee_flat if flat is None else flat
        fee = price * percent / Decimal(100) + flat
        if self.fee_cap is not None:
            fee = min(fee, self.fee_cap)
        return fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
