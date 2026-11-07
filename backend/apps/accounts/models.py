import hashlib
import hmac

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.phone import normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, phone, password, **extra):
        email = self.normalize_email(email).lower() if email else None
        phone = normalize_phone(phone) if phone else None
        if not email and not phone:
            raise ValueError("A user needs an email address or a phone number.")
        user = self.model(email=email, phone=phone, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email=None, phone=None, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, phone, password, **extra)

    def create_superuser(self, email, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("email_verified", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, extra.pop("phone", None), password, **extra)

    def get_by_identifier(self, identifier: str):
        """Look up a user by email or phone. Raises DoesNotExist."""
        identifier = (identifier or "").strip()
        if "@" in identifier:
            return self.get(email__iexact=identifier)
        return self.get(phone=normalize_phone(identifier))


class User(AbstractBaseUser, PermissionsMixin):
    """
    A person using the platform: ticket buyer, organizer team member, or staff.
    Signs in with email OR phone (at least one is required).
    """

    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(
        max_length=20, unique=True, null=True, blank=True, help_text="E.164, e.g. +233241234567"
    )
    full_name = models.CharField(max_length=150, blank=True)

    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    marketing_opt_in = models.BooleanField(
        default=False, help_text="Agreed to receive event recommendations and promotions."
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can log into the admin site.")
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(phone__isnull=False),
                name="user_has_email_or_phone",
            )
        ]

    def __str__(self):
        return self.full_name or self.email or self.phone or f"User {self.pk}"

    def save(self, *args, **kwargs):
        # Store "no value" as NULL so the unique constraints allow many blanks.
        self.email = self.email.lower().strip() if self.email else None
        self.phone = self.phone or None
        super().save(*args, **kwargs)

    @property
    def first_name(self):
        return self.full_name.split(" ")[0] if self.full_name else ""


class OTPPurpose(models.TextChoices):
    LOGIN = "login", "Login / sign up"
    VERIFY_CONTACT = "verify_contact", "Verify email or phone"
    PASSWORD_RESET = "password_reset", "Password reset"


class OTPCode(models.Model):
    """A one-time code sent by SMS or email. Only a hash of the code is stored."""

    target = models.CharField(max_length=254, db_index=True, help_text="Normalized email or phone")
    purpose = models.CharField(max_length=20, choices=OTPPurpose.choices)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["target", "purpose", "created_at"])]

    def __str__(self):
        return f"OTP {self.purpose} for {self.target}"

    @staticmethod
    def hash_code(code: str) -> str:
        return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()

    def matches(self, code: str) -> bool:
        return hmac.compare_digest(self.code_hash, self.hash_code(code))

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
