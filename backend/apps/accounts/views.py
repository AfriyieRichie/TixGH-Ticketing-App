from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.messaging import SMSError
from apps.orders.services import claim_guest_orders

from . import serializers as s
from .models import OTPPurpose
from .otp import Contact, OTPError, check_otp, issue_otp

User = get_user_model()


def _field_for(contact: Contact) -> str:
    return "email" if contact.is_email else "phone"


def _find_user(contact: Contact):
    return User.objects.filter(**{_field_for(contact): contact.value}).first()


def _auth_response(user, is_new_user=False, status_code=status.HTTP_200_OK):
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "is_new_user": is_new_user,
            "user": s.UserSerializer(user).data,
        },
        status=status_code,
    )


def _otp_error(exc: OTPError):
    return ValidationError({"code": [str(exc)]})


class OTPRequestView(APIView):
    """
    Send a one-time code by SMS (phone) or email.

    - `login`: works for new and existing users (accounts are created on verify).
    - `verify_contact`: signed-in users adding an email/phone to their account.
    - `password_reset`: always answers the same way, whether or not the account exists.
    """

    permission_classes = [AllowAny]
    throttle_scope = "otp_request"

    @extend_schema(request=s.OTPRequestSerializer, responses=s.OTPSentSerializer)
    def post(self, request):
        ser = s.OTPRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        contact: Contact = ser.validated_data["identifier"]
        purpose = ser.validated_data["purpose"]

        deliver = True
        if purpose == OTPPurpose.VERIFY_CONTACT:
            if not request.user.is_authenticated:
                raise AuthenticationFailed("Sign in to verify a new email or phone number.")
            owner = _find_user(contact)
            if owner and owner != request.user:
                raise ValidationError({"identifier": ["This is already linked to another account."]})
        elif purpose == OTPPurpose.PASSWORD_RESET:
            existing = _find_user(contact)
            deliver = bool(existing and existing.is_active)

        try:
            issue_otp(contact, purpose, deliver=deliver)
        except OTPError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except SMSError:
            return Response(
                {"detail": "We could not send the SMS right now. Please try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "channel": contact.channel,
                "sent_to": contact.masked,
                "expires_in_minutes": settings.OTP_TTL_MINUTES,
            }
        )


class OTPLoginView(APIView):
    """Exchange a login code for tokens. Creates the account on first login."""

    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"

    @extend_schema(request=s.OTPLoginSerializer, responses=s.AuthResponseSerializer)
    def post(self, request):
        ser = s.OTPLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        contact: Contact = ser.validated_data["identifier"]
        try:
            check_otp(contact, OTPPurpose.LOGIN, ser.validated_data["code"])
        except OTPError as exc:
            raise _otp_error(exc)

        field = _field_for(contact)
        user, created = User.objects.get_or_create(
            **{field: contact.value},
            defaults={"full_name": ser.validated_data.get("full_name", "").strip()},
        )
        if created:
            user.set_unusable_password()
        if not user.is_active:
            raise PermissionDenied("This account has been disabled.")
        setattr(user, f"{field}_verified", True)
        user.save()
        claim_guest_orders(user)
        return _auth_response(
            user, is_new_user=created, status_code=status.HTTP_201_CREATED if created else 200
        )


class PasswordLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    @extend_schema(request=s.PasswordLoginSerializer, responses=s.AuthResponseSerializer)
    def post(self, request):
        ser = s.PasswordLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authenticate(
            request,
            identifier=ser.validated_data["identifier"],
            password=ser.validated_data["password"],
        )
        if user is None:
            raise AuthenticationFailed("Incorrect email/phone or password.")
        return _auth_response(user)


class LogoutView(APIView):
    """Revoke a refresh token."""

    @extend_schema(request=s.LogoutSerializer, responses={205: None})
    def post(self, request):
        ser = s.LogoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            RefreshToken(ser.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # Already invalid: the outcome the client wanted.
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = s.UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class AttachContactView(APIView):
    """Add (or replace) the email or phone on the signed-in account after OTP check."""

    throttle_scope = "otp_verify"

    @extend_schema(request=s.AttachContactSerializer, responses=s.UserSerializer)
    def post(self, request):
        ser = s.AttachContactSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        contact: Contact = ser.validated_data["identifier"]
        owner = _find_user(contact)
        if owner and owner != request.user:
            raise ValidationError({"identifier": ["This is already linked to another account."]})
        try:
            check_otp(contact, OTPPurpose.VERIFY_CONTACT, ser.validated_data["code"])
        except OTPError as exc:
            raise _otp_error(exc)
        field = _field_for(contact)
        setattr(request.user, field, contact.value)
        setattr(request.user, f"{field}_verified", True)
        request.user.save()
        claim_guest_orders(request.user)
        return Response(s.UserSerializer(request.user).data)


class PasswordChangeView(APIView):
    """Set a password (OTP-only accounts) or change an existing one."""

    @extend_schema(request=s.PasswordChangeSerializer, responses={204: None})
    def post(self, request):
        ser = s.PasswordChangeSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"

    @extend_schema(request=s.PasswordResetSerializer, responses={204: None})
    def post(self, request):
        ser = s.PasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        contact: Contact = ser.validated_data["identifier"]
        user = _find_user(contact)
        if user is not None:
            # Validate first so a weak password doesn't burn the code.
            try:
                validate_password(ser.validated_data["new_password"], user)
            except DjangoValidationError as exc:
                raise ValidationError({"new_password": exc.messages})
        try:
            check_otp(contact, OTPPurpose.PASSWORD_RESET, ser.validated_data["code"])
        except OTPError as exc:
            raise _otp_error(exc)
        if user is None or not user.is_active:
            raise ValidationError({"code": ["This code has expired. Request a new one."]})
        user.set_password(ser.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)
