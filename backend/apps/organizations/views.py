import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.messaging import SMSError, send_email, send_sms

from . import serializers as s
from .models import (
    Invitation,
    Membership,
    Organization,
    PayoutAccount,
    Perm,
    Role,
    VerificationStatus,
)
from .permissions import OrgScopedMixin

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Organizations
# --------------------------------------------------------------------------
class OrganizationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Organizations the signed-in user belongs to. Creating one makes you its owner."""

    serializer_class = s.OrganizationSerializer
    lookup_field = "slug"
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Organization.objects.none()
        return Organization.objects.filter(
            memberships__user=self.request.user, is_active=True
        ).distinct()

    def _require(self, org, perm):
        m = org.membership_for(self.request.user)
        if not m or not m.can(perm):
            raise PermissionDenied("Your team role does not allow this action.")

    @transaction.atomic
    def perform_create(self, serializer):
        org = serializer.save(created_by=self.request.user)
        Membership.objects.create(organization=org, user=self.request.user, role=Role.OWNER)

    def perform_update(self, serializer):
        self._require(serializer.instance, Perm.MANAGE_ORG)
        serializer.save()

    @extend_schema(request=None)
    @action(detail=True, methods=["post"], url_path="submit-verification")
    def submit_verification(self, request, slug=None):
        """Ask the platform team to verify this organizer (adds a 'Verified' badge)."""
        org = self.get_object()
        self._require(org, Perm.MANAGE_ORG)
        if org.verification_status in (VerificationStatus.PENDING, VerificationStatus.VERIFIED):
            raise ValidationError({"detail": f"Verification is already {org.verification_status}."})
        missing = [f for f in ("description", "region") if not getattr(org, f)]
        if not (org.email or org.phone):
            missing.append("email or phone")
        if not org.payout_accounts.exists():
            missing.append("payout account")
        if missing:
            raise ValidationError({"detail": f"Complete your profile first: {', '.join(missing)}."})
        org.verification_status = VerificationStatus.PENDING
        org.verification_note = ""
        org.save(update_fields=["verification_status", "verification_note", "updated_at"])
        return Response(self.get_serializer(org).data)


class PublicOrganizationView(generics.RetrieveAPIView):
    """Public organizer profile page."""

    permission_classes = [AllowAny]
    serializer_class = s.PublicOrganizationSerializer
    lookup_field = "slug"
    queryset = Organization.objects.filter(is_active=True)


# --------------------------------------------------------------------------
# Team members
# --------------------------------------------------------------------------
def _owner_count(org) -> int:
    return org.memberships.filter(role=Role.OWNER).count()


class MemberListView(OrgScopedMixin, generics.ListAPIView):
    serializer_class = s.MembershipSerializer
    pagination_class = None

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()
        return self.organization.memberships.select_related("user")


class MemberDetailView(OrgScopedMixin, generics.GenericAPIView):
    """Change a member's role, or remove them. Anyone may remove themselves (leave)."""

    serializer_class = s.MembershipSerializer
    http_method_names = ["patch", "delete"]

    def get_required_perm(self):
        return None  # Checked per action below (leaving needs no permission).

    def get_object(self):
        return get_object_or_404(self.organization.memberships, pk=self.kwargs["pk"])

    def _check_can_manage(self, target: Membership, new_role: str | None = None):
        me = self.membership
        if not me.can(Perm.MANAGE_MEMBERS):
            raise PermissionDenied("Your team role does not allow this action.")
        touches_owner = target.role == Role.OWNER or new_role == Role.OWNER
        if touches_owner and me.role != Role.OWNER:
            raise PermissionDenied("Only an owner can add or change owners.")

    def patch(self, request, *args, **kwargs):
        target = self.get_object()
        ser = self.get_serializer(target, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        new_role = ser.validated_data.get("role", target.role)
        self._check_can_manage(target, new_role)
        if target.role == Role.OWNER and new_role != Role.OWNER and _owner_count(self.organization) == 1:
            raise ValidationError({"role": "An organization must keep at least one owner."})
        ser.save()
        return Response(ser.data)

    def delete(self, request, *args, **kwargs):
        target = self.get_object()
        if target.user_id != request.user.id:
            self._check_can_manage(target)
        if target.role == Role.OWNER and _owner_count(self.organization) == 1:
            raise ValidationError({"detail": "An organization must keep at least one owner."})
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Invitations
# --------------------------------------------------------------------------
def _send_invitation(invite: Invitation) -> bool:
    link = f"{settings.FRONTEND_URL}/invites/{invite.token}"
    inviter = invite.invited_by.full_name if invite.invited_by else "Someone"
    text = (
        f"{inviter} invited you to join {invite.organization.name} on {settings.PLATFORM_NAME} "
        f"as {invite.get_role_display()}. Accept here: {link}"
    )
    try:
        if "@" in invite.contact:
            send_email(invite.contact, f"Join {invite.organization.name} on {settings.PLATFORM_NAME}", text)
        else:
            send_sms(invite.contact, text)
        return True
    except (SMSError, OSError):
        logger.exception("Failed to deliver invitation %s", invite.pk)
        return False


class InvitationListCreateView(OrgScopedMixin, generics.ListCreateAPIView):
    serializer_class = s.InvitationSerializer
    required_perm = Perm.MANAGE_MEMBERS

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Invitation.objects.none()
        return self.organization.invitations.filter(accepted_at__isnull=True, revoked_at__isnull=True)

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        contact = ser.validated_data["contact"]
        role = ser.validated_data["role"]
        if role == Role.OWNER and self.membership.role != Role.OWNER:
            raise PermissionDenied("Only an owner can invite another owner.")
        field = "email" if contact.is_email else "phone"
        if self.organization.memberships.filter(**{f"user__{field}": contact.value}).exists():
            raise ValidationError({"contact": "This person is already on your team."})
        # Re-inviting replaces any pending invite for the same person.
        self.organization.invitations.filter(
            contact=contact.value, accepted_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        invite = Invitation.objects.create(
            organization=self.organization, contact=contact.value, role=role, invited_by=request.user
        )
        invite.delivery_failed = not _send_invitation(invite)
        return Response(self.get_serializer(invite).data, status=status.HTTP_201_CREATED)


class InvitationRevokeView(OrgScopedMixin, APIView):
    required_perm = Perm.MANAGE_MEMBERS

    @extend_schema(responses={204: None})
    def delete(self, request, org_slug, pk):
        invite = get_object_or_404(self.organization.invitations, pk=pk, accepted_at__isnull=True)
        invite.revoked_at = timezone.now()
        invite.save(update_fields=["revoked_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationByTokenView(APIView):
    """GET: preview an invite (no login needed). POST: accept it."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def _get(self, token):
        return get_object_or_404(Invitation.objects.select_related("organization"), token=token)

    @extend_schema(operation_id="invitation_preview", responses=s.InvitationPreviewSerializer)
    def get(self, request, token):
        return Response(s.InvitationPreviewSerializer(self._get(token)).data)

    @extend_schema(operation_id="invitation_accept", request=None, responses=s.OrganizationSerializer)
    def post(self, request, token):
        with transaction.atomic():
            invite = Invitation.objects.select_for_update().select_related("organization").get(
                pk=self._get(token).pk
            )
            if invite.status != "pending":
                raise ValidationError({"detail": f"This invitation is {invite.status}."})
            user = request.user
            if invite.contact not in (user.email, user.phone):
                raise PermissionDenied(
                    "This invitation was sent to a different email or phone number. "
                    "Sign in with that account to accept it."
                )
            Membership.objects.get_or_create(
                organization=invite.organization,
                user=user,
                defaults={"role": invite.role, "invited_by": invite.invited_by},
            )
            invite.accepted_at = timezone.now()
            invite.accepted_by = user
            invite.save(update_fields=["accepted_at", "accepted_by"])
        return Response(
            s.OrganizationSerializer(invite.organization, context={"request": request}).data
        )


# --------------------------------------------------------------------------
# Payout accounts
# --------------------------------------------------------------------------
class PayoutAccountViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = s.PayoutAccountSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_required_perm(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return Perm.VIEW_FINANCE
        return Perm.MANAGE_PAYOUTS

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PayoutAccount.objects.none()
        return self.organization.payout_accounts.all()

    @transaction.atomic
    def perform_create(self, serializer):
        is_first = not self.organization.payout_accounts.exists()
        make_default = is_first or serializer.validated_data.get("is_default", False)
        if make_default:
            self.organization.payout_accounts.filter(is_default=True).update(is_default=False)
        serializer.save(organization=self.organization, is_default=make_default)

    @transaction.atomic
    def perform_update(self, serializer):
        details_changed = any(
            f in serializer.validated_data
            and serializer.validated_data[f] != getattr(serializer.instance, f)
            for f in ("method", "account_number", "bank_code", "mobile_money_provider")
        )
        if serializer.validated_data.get("is_default"):
            self.organization.payout_accounts.exclude(pk=serializer.instance.pk).filter(
                is_default=True
            ).update(is_default=False)
        extra = {"is_verified": False, "gateway_subaccount_code": ""} if details_changed else {}
        serializer.save(**extra)

    def perform_destroy(self, instance):
        if instance.is_default and self.organization.payout_accounts.count() > 1:
            raise ValidationError({"detail": "Make another account the default before deleting this one."})
        instance.delete()
