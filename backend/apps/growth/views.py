from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.db.models import Count, F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.models import Event, EventStatus
from apps.orders.models import OrderStatus, Ticket
from apps.organizations.models import Organization, Perm
from apps.organizations.permissions import OrgScopedMixin

from . import services
from .models import Campaign, CampaignStatus, Follow, Review, TrackingLink, Unsubscribe

SAFE = ("GET", "HEAD", "OPTIONS")


# --------------------------------------------------------------------------
# Following organizers
# --------------------------------------------------------------------------
class FollowView(APIView):
    """GET: follow status and count. POST: follow. DELETE: unfollow."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def _org(self, slug):
        return get_object_or_404(Organization, slug=slug, is_active=True)

    def _state(self, request, org):
        following = request.user.is_authenticated and Follow.objects.filter(user=request.user, organization=org).exists()
        return Response({"following": following, "followers": Follow.objects.filter(organization=org).count()})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, slug):
        return self._state(request, self._org(slug))

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, slug):
        org = self._org(slug)
        Follow.objects.get_or_create(user=request.user, organization=org)
        if request.user.email:  # following again re-enables their emails
            Unsubscribe.objects.filter(organization=org, email=request.user.email.lower()).delete()
        return self._state(request, org)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def delete(self, request, slug):
        org = self._org(slug)
        Follow.objects.filter(user=request.user, organization=org).delete()
        return self._state(request, org)


class FollowingListView(APIView):
    """Organizers the signed-in user follows."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        rows = Follow.objects.filter(user=request.user).select_related("organization").order_by("organization__name")
        return Response([{"name": f.organization.name, "slug": f.organization.slug,
                          "is_verified": f.organization.is_verified} for f in rows])


# --------------------------------------------------------------------------
# Tracking links
# --------------------------------------------------------------------------
class RefClickView(APIView):
    """The web app reports a visit through a ?ref= link (counted for the organizer)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, slug, code):
        link = TrackingLink.objects.filter(event__slug=slug, code__iexact=code, is_active=True).first()
        if link:
            TrackingLink.objects.filter(pk=link.pk).update(clicks=F("clicks") + 1)
        return Response({"valid": bool(link)})


class TrackingLinkSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    orders = serializers.IntegerField(source="orders_count", read_only=True, default=0)
    tickets = serializers.IntegerField(source="tickets_count", read_only=True, default=0)
    revenue = serializers.DecimalField(source="revenue_sum", max_digits=12, decimal_places=2, read_only=True,
                                       default=Decimal("0"))
    commission = serializers.SerializerMethodField()
    # Explicit default: form-encoded requests would otherwise read a missing checkbox as False.
    is_active = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = TrackingLink
        fields = ["id", "code", "label", "commission_percent", "is_active", "clicks", "orders", "tickets",
                  "revenue", "commission", "url", "created_at"]
        read_only_fields = ["clicks", "created_at"]

    def get_url(self, obj) -> str:
        return f"{settings.FRONTEND_URL}/e/{obj.event.slug}?ref={obj.code}"

    def get_commission(self, obj) -> str | None:
        if obj.commission_percent is None:
            return None
        revenue = getattr(obj, "revenue_sum", None) or Decimal("0")
        return str((revenue * obj.commission_percent / 100).quantize(Decimal("0.01")))

    def validate_code(self, value):
        value = value.strip().lower()
        event = self.context["event"]
        qs = TrackingLink.objects.filter(event=event, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This event already has a link with that code.")
        return value


class TrackingLinkViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = TrackingLinkSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]
    required_perm = Perm.MANAGE_EVENTS

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.event = get_object_or_404(self.organization.events, slug=kwargs["event_slug"])

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "event": getattr(self, "event", None)}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TrackingLink.objects.none()
        paid = Q(orders__status=OrderStatus.PAID)
        return (
            self.event.tracking_links.select_related("event")
            .annotate(
                orders_count=Count("orders", filter=paid, distinct=True),
                revenue_sum=Sum("orders__organizer_amount", filter=paid),
            )
        )

    def list(self, request, *args, **kwargs):
        links = list(self.get_queryset())
        tickets = dict(
            Ticket.objects.filter(order__tracking_link__in=links, order__status=OrderStatus.PAID)
            .values_list("order__tracking_link").annotate(n=Count("id"))
        )
        for link in links:
            link.revenue_sum = link.revenue_sum or Decimal("0")
            link.tickets_count = tickets.get(link.pk, 0)
        return Response(self.get_serializer(links, many=True).data)

    def perform_create(self, serializer):
        serializer.save(event=self.event, created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.orders.exists():
            raise ValidationError({"detail": "This link has sales. Switch it off instead."})
        instance.delete()


# --------------------------------------------------------------------------
# Reviews
# --------------------------------------------------------------------------
class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ["id", "rating", "comment", "author", "organizer_reply", "replied_at", "created_at"]
        read_only_fields = ["organizer_reply", "replied_at", "created_at"]

    def get_author(self, obj) -> str:
        name = (obj.user.full_name or "Attendee").split(" ")
        return name[0] + (f" {name[-1][0]}." if len(name) > 1 else "")


def _can_review(user, event) -> tuple[bool, str]:
    if not user.is_authenticated:
        return False, "Sign in to review."
    if event.start_at > timezone.now():
        return False, "You can review once the event has started."
    attended = Ticket.objects.filter(event=event).filter(Q(holder=user) | Q(order__user=user)) \
        .filter(order__status=OrderStatus.PAID).exists()
    if not attended:
        return False, "Only ticket holders can review this event."
    return True, ""


class EventReviewsView(APIView):
    """GET: reviews + average. POST: write or update your review (ticket holders, after the event starts)."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [IsAuthenticated()]

    def _event(self, slug):
        return get_object_or_404(Event, slug=slug, status__in=[EventStatus.PUBLISHED, EventStatus.CANCELLED])

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, slug):
        event = self._event(slug)
        qs = event.reviews.filter(is_hidden=False).select_related("user")
        can, reason = _can_review(request.user, event)
        mine = qs.filter(user=request.user).first() if request.user.is_authenticated else None
        return Response({
            **services.rating_summary(event.reviews.all()),
            "reviews": ReviewSerializer(qs[:50], many=True).data,
            "can_review": can, "reason": reason,
            "mine": ReviewSerializer(mine).data if mine else None,
        })

    @extend_schema(request=ReviewSerializer, responses=ReviewSerializer)
    def post(self, request, slug):
        event = self._event(slug)
        can, reason = _can_review(request.user, event)
        if not can:
            raise PermissionDenied(reason)
        ser = ReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        review, _ = Review.objects.update_or_create(
            event=event, user=request.user,
            defaults={"rating": ser.validated_data["rating"], "comment": ser.validated_data.get("comment", "")},
        )
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class ReplySerializer(serializers.Serializer):
    reply = serializers.CharField(max_length=2000, allow_blank=True)


class ReviewReplyView(OrgScopedMixin, APIView):
    required_perm = Perm.MANAGE_EVENTS

    @extend_schema(request=ReplySerializer, responses=ReviewSerializer)
    def post(self, request, org_slug, event_slug, pk):
        review = get_object_or_404(Review, pk=pk, event__slug=event_slug, event__organization=self.organization)
        ser = ReplySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        review.organizer_reply = ser.validated_data["reply"]
        review.replied_at = timezone.now() if review.organizer_reply else None
        review.save(update_fields=["organizer_reply", "replied_at", "updated_at"])
        return Response(ReviewSerializer(review).data)


# --------------------------------------------------------------------------
# Audience & campaigns
# --------------------------------------------------------------------------
class AudienceView(OrgScopedMixin, APIView):
    required_perm = Perm.MANAGE_EVENTS

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_slug):
        return Response(services.audience_summary(self.organization))


class CampaignSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(slug_field="slug", queryset=Event.objects.none(), required=False, allow_null=True)

    class Meta:
        model = Campaign
        fields = ["id", "subject", "body", "event", "audience", "status", "automatic", "recipients_count",
                  "sent_count", "failed_count", "queued_at", "finished_at", "created_at"]
        read_only_fields = ["status", "automatic", "recipients_count", "sent_count", "failed_count",
                            "queued_at", "finished_at", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        org = self.context.get("organization")
        if org is not None:
            self.fields["event"].queryset = org.events.filter(status=EventStatus.PUBLISHED)


class CampaignViewSet(OrgScopedMixin, viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    required_perm = Perm.MANAGE_EVENTS
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Campaign.objects.none()
        return self.organization.campaigns.select_related("event")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "organization": getattr(self, "organization", None)}

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, created_by=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.status != CampaignStatus.DRAFT:
            raise ValidationError({"detail": "Sent campaigns can't be edited."})
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status != CampaignStatus.DRAFT:
            raise ValidationError({"detail": "Sent campaigns can't be deleted."})
        instance.delete()

    @extend_schema(request=None, responses=CampaignSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request, org_slug=None, pk=None):
        campaign = self.get_object()
        try:
            services.queue_campaign(campaign)
        except services.CampaignError as exc:
            raise ValidationError({"detail": str(exc)})
        services.process_campaigns()  # start right away; the scheduler continues the rest
        campaign.refresh_from_db()
        return Response(self.get_serializer(campaign).data)


# --------------------------------------------------------------------------
# Unsubscribe page (linked from every campaign email)
# --------------------------------------------------------------------------
@csrf_protect
def unsubscribe_page(request, token):
    try:
        org_id, email = services.read_unsubscribe_token(token)
        org = Organization.objects.get(pk=org_id)
    except (signing.BadSignature, Organization.DoesNotExist):
        return render(request, "growth/unsubscribe.html", {"invalid": True}, status=400)
    if request.method == "POST":
        Unsubscribe.objects.get_or_create(organization=org, email=email)
        return render(request, "growth/unsubscribe.html", {"done": True, "org": org, "email": email})
    if request.method != "GET":
        raise Http404
    return render(request, "growth/unsubscribe.html", {"org": org, "email": email})
