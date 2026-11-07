import secrets
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.core.constants import GhanaRegion, MobileMoneyProvider
from apps.core.models import FeeBearer, TimeStampedModel


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    FINANCE = "finance", "Finance"
    MARKETING = "marketing", "Marketing"
    SCANNER = "scanner", "Gate scanner"


class Perm:
    """What each team role can do inside an organization."""

    MANAGE_ORG = "manage_org"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_EVENTS = "manage_events"
    VIEW_FINANCE = "view_finance"
    MANAGE_PAYOUTS = "manage_payouts"
    SCAN_TICKETS = "scan_tickets"

    BY_ROLE = {
        Role.OWNER: {MANAGE_ORG, MANAGE_MEMBERS, MANAGE_EVENTS, VIEW_FINANCE, MANAGE_PAYOUTS, SCAN_TICKETS},
        Role.ADMIN: {MANAGE_ORG, MANAGE_MEMBERS, MANAGE_EVENTS, VIEW_FINANCE, SCAN_TICKETS},
        Role.FINANCE: {VIEW_FINANCE, MANAGE_PAYOUTS},
        Role.MARKETING: {MANAGE_EVENTS},
        Role.SCANNER: {SCAN_TICKETS},
    }

    @classmethod
    def for_role(cls, role: str) -> set[str]:
        return cls.BY_ROLE.get(role, set())


class VerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Not submitted"
    PENDING = "pending", "Pending review"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


# Slugs that would collide with URL paths under /organizations/.
RESERVED_SLUGS = {"public", "invitations", "new", "admin", "api"}


class Organization(TimeStampedModel):
    """An event organizer: a company, church, school, promoter or individual."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="org_logos/", blank=True)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    instagram = models.CharField(max_length=60, blank=True)
    x_handle = models.CharField("X (Twitter)", max_length=60, blank=True)
    facebook = models.CharField(max_length=120, blank=True)
    tiktok = models.CharField(max_length=60, blank=True)

    region = models.CharField(max_length=20, choices=GhanaRegion.choices, blank=True)
    city = models.CharField(max_length=80, blank=True)

    verification_status = models.CharField(
        max_length=12, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED
    )
    verification_note = models.TextField(blank=True, help_text="Shown to the organizer if rejected.")
    verified_at = models.DateTimeField(null=True, blank=True)

    # Commercial terms. Blank = use the platform defaults (see Platform settings).
    fee_bearer = models.CharField(max_length=12, choices=FeeBearer.choices, blank=True)
    fee_percent_override = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
        help_text="Negotiated or plan-based percentage fee.",
    )
    fee_flat_override = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )

    is_active = models.BooleanField(default=True, help_text="Inactive organizers cannot sell tickets.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Membership",
        through_fields=("organization", "user"),
        related_name="organizations",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if self.verification_status == VerificationStatus.VERIFIED and not self.verified_at:
            self.verified_at = timezone.now()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        base = slugify(self.name)[:150] or "organizer"
        slug, n = base, 2
        while (
            slug in RESERVED_SLUGS
            or Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists()
        ):
            slug = f"{base}-{n}"
            n += 1
        return slug

    @property
    def is_verified(self) -> bool:
        return self.verification_status == VerificationStatus.VERIFIED

    def membership_for(self, user):
        if not user or not user.is_authenticated:
            return None
        return self.memberships.filter(user=user).first()


class Membership(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=12, choices=Role.choices)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="unique_org_member")
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"

    @property
    def permissions(self) -> set[str]:
        return Perm.for_role(self.role)

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def _invite_token() -> str:
    return secrets.token_urlsafe(32)


def _invite_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(models.Model):
    """An invite to join an organizer's team, sent by SMS or email."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    contact = models.CharField(max_length=254, help_text="Normalized email or E.164 phone")
    role = models.CharField(max_length=12, choices=Role.choices)
    token = models.CharField(max_length=64, unique=True, default=_invite_token, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite {self.contact} to {self.organization} as {self.role}"

    @property
    def status(self) -> str:
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if timezone.now() >= self.expires_at:
            return "expired"
        return "pending"


class PayoutMethod(models.TextChoices):
    MOBILE_MONEY = "mobile_money", "Mobile Money"
    BANK = "bank", "Bank account"


class PayoutAccount(TimeStampedModel):
    """Where an organizer's ticket revenue is settled."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payout_accounts")
    method = models.CharField(max_length=15, choices=PayoutMethod.choices)
    mobile_money_provider = models.CharField(
        max_length=12, choices=MobileMoneyProvider.choices, blank=True
    )
    bank_name = models.CharField(max_length=100, blank=True)
    bank_code = models.CharField(max_length=20, blank=True, help_text="Paystack bank code")
    account_number = models.CharField(max_length=30)
    account_name = models.CharField(max_length=150)
    is_default = models.BooleanField(default=False)

    # Filled in once the account is registered with the payment gateway (Phase 3).
    gateway_subaccount_code = models.CharField(max_length=60, blank=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(is_default=True),
                name="one_default_payout_account_per_org",
            )
        ]
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.get_method_display()} {self.masked_account_number} ({self.account_name})"

    @property
    def masked_account_number(self) -> str:
        n = self.account_number
        return f"****{n[-4:]}" if len(n) > 4 else n
