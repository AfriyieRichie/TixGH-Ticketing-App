from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.core.phone import InvalidPhoneNumber

from .models import OTPPurpose
from .otp import parse_contact

User = get_user_model()


class ContactField(serializers.CharField):
    """Accepts an email or a (Ghana-local or international) phone number."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return parse_contact(value)
        except InvalidPhoneNumber as exc:
            raise serializers.ValidationError(str(exc))


class UserSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "email_verified",
            "phone_verified",
            "marketing_opt_in",
            "has_password",
            "date_joined",
        ]
        read_only_fields = [
            "email",
            "phone",
            "email_verified",
            "phone_verified",
            "has_password",
            "date_joined",
        ]

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()


class OTPRequestSerializer(serializers.Serializer):
    identifier = ContactField(help_text="Email address or phone number, e.g. 0241234567")
    purpose = serializers.ChoiceField(choices=OTPPurpose.choices, default=OTPPurpose.LOGIN)


class OTPLoginSerializer(serializers.Serializer):
    identifier = ContactField()
    code = serializers.CharField(max_length=10)
    full_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, help_text="Used when a new account is created."
    )


class PasswordLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)


class AttachContactSerializer(serializers.Serializer):
    identifier = ContactField()
    code = serializers.CharField(max_length=10)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=False, trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password() and not user.check_password(
            attrs.get("current_password", "")
        ):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    identifier = ContactField()
    code = serializers.CharField(max_length=10)
    new_password = serializers.CharField(trim_whitespace=False)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class AuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    is_new_user = serializers.BooleanField()
    user = UserSerializer()


class OTPSentSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=["sms", "email"])
    sent_to = serializers.CharField(help_text="Masked destination, e.g. +233 24 *** 4567")
    expires_in_minutes = serializers.IntegerField()
