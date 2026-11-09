from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.serializers import ContactField
from apps.growth.models import Review
from apps.growth.services import rating_summary
from apps.core.phone import InvalidPhoneNumber, normalize_phone

from .models import Invitation, Membership, Organization, PayoutAccount, PayoutMethod

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    my_role = serializers.SerializerMethodField()
    my_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id", "name", "slug", "description", "logo",
            "email", "phone", "website", "instagram", "x_handle", "facebook", "tiktok",
            "region", "city",
            "verification_status", "verification_note", "verified_at",
            "fee_bearer", "fee_percent_override", "fee_flat_override",
            "my_role", "my_permissions", "created_at",
        ]
        read_only_fields = [
            "slug", "verification_status", "verification_note", "verified_at",
            "fee_percent_override", "fee_flat_override", "created_at",
        ]

    def _membership(self, obj):
        cache = self.context.setdefault("_memberships", {})
        if obj.pk not in cache:
            cache[obj.pk] = obj.membership_for(self.context["request"].user)
        return cache[obj.pk]

    def get_my_role(self, obj) -> str | None:
        m = self._membership(obj)
        return m.role if m else None

    def get_my_permissions(self, obj) -> list[str]:
        m = self._membership(obj)
        return sorted(m.permissions) if m else []

    def validate_phone(self, value):
        if not value:
            return value
        try:
            return normalize_phone(value)
        except InvalidPhoneNumber as exc:
            raise serializers.ValidationError(str(exc))


class PublicOrganizationSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    followers = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "name", "slug", "description", "logo", "website",
            "instagram", "x_handle", "facebook", "tiktok",
            "region", "city", "is_verified", "followers", "rating",
        ]

    def get_followers(self, obj) -> int:
        return obj.followers.count()

    def get_rating(self, obj) -> dict:
        return rating_summary(Review.objects.filter(event__organization=obj))


class MemberUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "full_name", "email", "phone"]


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class InvitationSerializer(serializers.ModelSerializer):
    contact = ContactField(help_text="Email or phone number of the person to invite")
    status = serializers.CharField(read_only=True)
    delivery_failed = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Invitation
        fields = ["id", "contact", "role", "status", "created_at", "expires_at", "delivery_failed"]
        read_only_fields = ["id", "status", "created_at", "expires_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["contact"] = instance.contact
        return data


class InvitationPreviewSerializer(serializers.ModelSerializer):
    organization = PublicOrganizationSerializer(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Invitation
        fields = ["organization", "role", "status", "expires_at"]


class PayoutAccountSerializer(serializers.ModelSerializer):
    masked_account_number = serializers.CharField(read_only=True)

    class Meta:
        model = PayoutAccount
        fields = [
            "id", "method", "mobile_money_provider", "bank_name", "bank_code",
            "account_number", "masked_account_number", "account_name",
            "is_default", "is_verified", "created_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at"]

    def validate(self, attrs):
        get = lambda f: attrs.get(f, getattr(self.instance, f, ""))  # noqa: E731
        method = get("method")
        if method == PayoutMethod.MOBILE_MONEY:
            if not get("mobile_money_provider"):
                raise serializers.ValidationError(
                    {"mobile_money_provider": "Choose the Mobile Money network."}
                )
            if "account_number" in attrs:
                try:
                    e164 = normalize_phone(attrs["account_number"])
                except InvalidPhoneNumber:
                    raise serializers.ValidationError(
                        {"account_number": "Enter a valid Mobile Money number."}
                    )
                attrs["account_number"] = "0" + e164[4:]  # Gateways expect local format.
            attrs["bank_name"] = ""
            attrs["bank_code"] = ""
        elif method == PayoutMethod.BANK:
            if not get("bank_name") or not get("bank_code"):
                raise serializers.ValidationError({"bank_code": "Choose the bank."})
            attrs["mobile_money_provider"] = ""
        return attrs
