from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.dispatch import dispatch
from apps.growth.services import notify_followers_of_new_event
from apps.notifications.tasks import deliver_cancellation
from apps.organizations.models import Perm
from apps.organizations.permissions import OrgScopedMixin

from . import serializers as s
from .models import Category, Event, EventStatus, PromoCode, TicketType, TicketVisibility, Venue
from .pricing import price_breakdown

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class _EventsPermMixin(OrgScopedMixin):
    """Any team member can view; changes need the manage_events permission."""

    def get_required_perm(self):
        return None if self.request.method in SAFE_METHODS else Perm.MANAGE_EVENTS


# --------------------------------------------------------------------------
# Organizer: venues
# --------------------------------------------------------------------------
class VenueViewSet(_EventsPermMixin, viewsets.ModelViewSet):
    serializer_class = s.VenueSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Venue.objects.none()
        return self.organization.venues.all()

    def perform_create(self, serializer):
        serializer.save(organization=self.organization)

    def perform_destroy(self, instance):
        if instance.events.filter(status=EventStatus.PUBLISHED, end_at__gte=timezone.now()).exists():
            raise ValidationError({"detail": "This venue is used by an upcoming published event."})
        instance.delete()


# --------------------------------------------------------------------------
# Organizer: events
# --------------------------------------------------------------------------
class EventViewSet(_EventsPermMixin, viewsets.ModelViewSet):
    """Events of one organization (drafts included)."""

    serializer_class = s.EventSerializer
    lookup_field = "slug"
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Event.objects.none()
        qs = (
            self.organization.events.select_related("venue", "category", "organization")
            .prefetch_related("ticket_types", "organization__payout_accounts")
            .order_by("-start_at")
        )
        if st := self.request.query_params.get("status"):
            qs = qs.filter(status=st)
        when = self.request.query_params.get("when")
        if when == "upcoming":
            qs = qs.filter(end_at__gte=timezone.now()).order_by("start_at")
        elif when == "past":
            qs = qs.filter(end_at__lt=timezone.now())
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["organization"] = getattr(self, "organization", None)
        return ctx

    def perform_create(self, serializer):
        serializer.save(organization=self.organization, created_by=self.request.user)

    def perform_destroy(self, event):
        if event.tickets_sold:
            raise ValidationError({"detail": "Events with ticket sales can't be deleted. Cancel it instead."})
        event.delete()

    def _respond(self, event):
        event = self.get_queryset().get(pk=event.pk)  # re-fetch with prefetches
        return Response(self.get_serializer(event).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def publish(self, request, org_slug=None, slug=None):
        event = self.get_object()
        if event.status != EventStatus.DRAFT:
            raise ValidationError({"detail": f"Only drafts can be published (this event is {event.status})."})
        if problems := event.publish_problems():
            raise ValidationError({"detail": "This event isn't ready to publish.", "problems": problems})
        event.status = EventStatus.PUBLISHED
        first_publish = event.published_at is None
        event.published_at = event.published_at or timezone.now()
        event.save(update_fields=["status", "published_at", "updated_at"])
        if first_publish:
            notify_followers_of_new_event(event)
        return self._respond(event)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def unpublish(self, request, org_slug=None, slug=None):
        """Take a published event back to draft (only before any tickets are sold)."""
        event = self.get_object()
        if event.status != EventStatus.PUBLISHED:
            raise ValidationError({"detail": "Only published events can be unpublished."})
        if event.tickets_sold:
            raise ValidationError({"detail": "Tickets have been sold. Cancel the event instead."})
        event.status = EventStatus.DRAFT
        event.save(update_fields=["status", "updated_at"])
        return self._respond(event)

    @extend_schema(request=s.CancelEventSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, org_slug=None, slug=None):
        """Cancel the event. Ticket holders will be notified and refunded (Phase 3/4)."""
        event = self.get_object()
        ser = s.CancelEventSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if event.status == EventStatus.CANCELLED:
            raise ValidationError({"detail": "This event is already cancelled."})
        if event.has_ended:
            raise ValidationError({"detail": "This event has already ended."})
        event.status = EventStatus.CANCELLED
        event.cancelled_at = timezone.now()
        event.cancellation_reason = ser.validated_data["reason"]
        event.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
        event_pk = event.pk
        transaction.on_commit(lambda: dispatch(deliver_cancellation, event_pk))
        return self._respond(event)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def duplicate(self, request, org_slug=None, slug=None):
        """Copy an event (with ticket types and promo codes) into a new draft."""
        src = self.get_object()
        with transaction.atomic():
            copy = Event.objects.get(pk=src.pk)
            copy.pk = copy.id = None
            copy.slug = ""
            copy.title = f"{src.title} (copy)"[:150]
            copy.status = EventStatus.DRAFT
            copy.is_featured = False
            copy.published_at = copy.cancelled_at = None
            copy.cancellation_reason = ""
            copy.created_by = request.user
            copy.save()
            type_map = {}
            for t in src.ticket_types.all():
                old_pk = t.pk
                t.pk = t.id = None
                t.event = copy
                t.quantity_sold = 0
                t.save()
                type_map[old_pk] = t
            for p in src.promo_codes.prefetch_related("ticket_types"):
                linked = [type_map[tt.pk] for tt in p.ticket_types.all() if tt.pk in type_map]
                p.pk = p.id = None
                p.event = copy
                p.times_used = 0
                p.save()
                p.ticket_types.set(linked)
        return Response(
            self.get_serializer(self.get_queryset().get(pk=copy.pk)).data, status=status.HTTP_201_CREATED
        )


class _EventChildMixin(_EventsPermMixin):
    """For /organizations/<org>/events/<event_slug>/<children>/."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.event = get_object_or_404(self.organization.events, slug=kwargs["event_slug"])
        if request.method not in SAFE_METHODS and self.event.status == EventStatus.CANCELLED:
            raise ValidationError({"detail": "Cancelled events can't be edited."})

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["event"] = getattr(self, "event", None)
        return ctx


class TicketTypeViewSet(_EventChildMixin, viewsets.ModelViewSet):
    serializer_class = s.TicketTypeSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TicketType.objects.none()
        return self.event.ticket_types.select_related("event__organization")

    def perform_create(self, serializer):
        serializer.save(event=self.event)

    def perform_destroy(self, instance):
        if instance.quantity_sold:
            raise ValidationError({"detail": "This ticket type has sales. Deactivate it instead."})
        instance.delete()


class PromoCodeViewSet(_EventChildMixin, viewsets.ModelViewSet):
    serializer_class = s.PromoCodeSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PromoCode.objects.none()
        return self.event.promo_codes.prefetch_related("ticket_types")

    def perform_create(self, serializer):
        serializer.save(event=self.event)

    def perform_destroy(self, instance):
        if instance.times_used:
            raise ValidationError({"detail": "This code has been used. Deactivate it instead."})
        instance.delete()


# --------------------------------------------------------------------------
# Public discovery
# --------------------------------------------------------------------------
class CategoryListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.CategorySerializer
    pagination_class = None
    queryset = Category.objects.filter(is_active=True)


def _date_window(preset: str):
    """Return (start, end) in local time for a date preset, or None."""
    now = timezone.localtime()
    today = now.date()
    tz = timezone.get_current_timezone()

    def day_start(d):
        return datetime.combine(d, time.min, tzinfo=tz)

    if preset == "today":
        return now, day_start(today + timedelta(days=1))
    if preset == "tomorrow":
        return day_start(today + timedelta(days=1)), day_start(today + timedelta(days=2))
    if preset == "this_weekend":  # Friday 17:00 to Sunday midnight
        friday = today + timedelta(days=(4 - today.weekday()) % 7)
        if today.weekday() == 6:  # Sunday: the weekend is now
            friday = today - timedelta(days=2)
        start = max(now, datetime.combine(friday, time(17, 0), tzinfo=tz))
        return start, day_start(friday + timedelta(days=3))
    if preset == "this_week":
        return now, day_start(today + timedelta(days=7 - today.weekday()))
    if preset == "next_7_days":
        return now, now + timedelta(days=7)
    if preset == "this_month":
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        return now, day_start(nxt)
    return None


_LIST_PARAMS = [
    OpenApiParameter("q", str, description="Search title, description, venue, organizer"),
    OpenApiParameter("category", str, description="Category slug"),
    OpenApiParameter("region", str), OpenApiParameter("city", str),
    OpenApiParameter("organizer", str, description="Organizer slug"),
    OpenApiParameter(
        "when", str, enum=["today", "tomorrow", "this_weekend", "this_week", "next_7_days", "this_month"]
    ),
    OpenApiParameter("date_from", OpenApiTypes.DATE), OpenApiParameter("date_to", OpenApiTypes.DATE),
    OpenApiParameter("price", str, enum=["free", "paid"]),
    OpenApiParameter("format", str, enum=["in_person", "online", "hybrid"]),
    OpenApiParameter("featured", bool),
    OpenApiParameter("sort", str, enum=["date", "newest", "trending"]),
]


class PublicEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Browse and search published events."""

    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_serializer_class(self):
        return s.PublicEventDetailSerializer if self.action == "retrieve" else s.PublicEventListSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **s.platform_context()}

    def _base(self, qs):
        return qs.select_related("venue", "category", "organization").prefetch_related(
            Prefetch("ticket_types", queryset=TicketType.objects.filter(is_active=True))
        )

    def get_queryset(self):
        if self.action == "retrieve":
            # Unlisted and cancelled events are reachable by direct link.
            return self._base(
                Event.objects.filter(
                    status__in=[EventStatus.PUBLISHED, EventStatus.CANCELLED], organization__is_active=True
                )
            )
        qs = self._base(Event.objects.listed())
        p = self.request.query_params
        if q := p.get("q", "").strip():
            qs = qs.filter(
                Q(title__icontains=q) | Q(summary__icontains=q) | Q(description__icontains=q)
                | Q(venue__name__icontains=q) | Q(venue__city__icontains=q)
                | Q(organization__name__icontains=q) | Q(category__name__icontains=q)
            )
        if v := p.get("category"):
            qs = qs.filter(category__slug=v)
        if v := p.get("region"):
            qs = qs.filter(venue__region=v)
        if v := p.get("city"):
            qs = qs.filter(venue__city__iexact=v)
        if v := p.get("organizer"):
            qs = qs.filter(organization__slug=v)
        if v := p.get("format"):
            qs = qs.filter(format=v)
        if p.get("featured") in ("1", "true", "True"):
            qs = qs.filter(is_featured=True)
        if (v := p.get("price")) in ("free", "paid"):
            visible = Q(ticket_types__is_active=True, ticket_types__visibility=TicketVisibility.VISIBLE)
            price_q = Q(ticket_types__price=0) if v == "free" else Q(ticket_types__price__gt=0)
            qs = qs.filter(visible & price_q)
        window = _date_window(p.get("when", ""))
        if window is None and (p.get("date_from") or p.get("date_to")):
            try:
                tz = timezone.get_current_timezone()
                start = (
                    datetime.combine(datetime.fromisoformat(p["date_from"]).date(), time.min, tzinfo=tz)
                    if p.get("date_from") else None
                )
                end = (
                    datetime.combine(datetime.fromisoformat(p["date_to"]).date(), time.max, tzinfo=tz)
                    if p.get("date_to") else None
                )
            except ValueError:
                raise ValidationError({"detail": "Dates must be in YYYY-MM-DD format."})
            window = (start, end)
        if window:
            start, end = window
            if start:
                qs = qs.filter(end_at__gte=start)
            if end:
                qs = qs.filter(start_at__lt=end)
        qs = qs.distinct()
        if p.get("sort") == "newest":
            return qs.order_by("-published_at")
        if p.get("sort") == "trending":
            week = timezone.now() - timedelta(days=7)
            return qs.annotate(
                recent_sales=Count("orders", filter=Q(orders__status="paid", orders__paid_at__gte=week), distinct=True)
            ).order_by("-recent_sales", "start_at")
        return qs.order_by("start_at")

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(responses=s.PublicEventListSerializer(many=True))
    @action(detail=True, methods=["get"])
    def similar(self, request, slug=None):
        """Up to 6 upcoming events in the same category or by the same organizer."""
        event = self.get_object()
        qs = self._base(Event.objects.listed()).exclude(pk=event.pk).filter(
            Q(category_id=event.category_id) | Q(organization_id=event.organization_id)
        ).order_by("start_at")[:6]
        return Response(s.PublicEventListSerializer(qs, many=True, context=self.get_serializer_context()).data)

    @extend_schema(request=s.PromoCheckSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="promo-check")
    def promo_check(self, request, slug=None):
        """
        Check a promo / access code before checkout. Returns the discounted
        prices and any hidden ticket types the code unlocks.
        """
        event = self.get_object()
        ser = s.PromoCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        code = ser.validated_data["code"].strip().upper()
        promo = event.promo_codes.prefetch_related("ticket_types").filter(code=code).first()
        if promo is None:
            raise ValidationError({"code": ["This code isn't valid for this event."]})
        if problem := promo.problem():
            raise ValidationError({"code": [problem]})

        platform = self.get_serializer_context()["platform"]
        applicable = [t for t in event.ticket_types.all() if t.is_active and promo.applies_to(t)]
        return Response(
            {
                "code": promo.code,
                "discount_type": promo.discount_type,
                "amount": str(promo.amount),
                "ticket_types": [
                    {
                        "id": t.pk,
                        "name": t.name,
                        "hidden": t.visibility == TicketVisibility.HIDDEN,
                        "sale_status": t.sale_status,
                        "original": price_breakdown(event, t.price, platform).as_dict(),
                        "discounted": price_breakdown(event, promo.discounted_price(t.price), platform).as_dict(),
                    }
                    for t in applicable
                ],
            }
        )
