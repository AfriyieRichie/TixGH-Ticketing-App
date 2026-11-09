from datetime import timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.models import Event, EventStatus
from apps.orders.models import Ticket
from apps.organizations.models import Membership, Perm
from apps.tickets.rendering import format_when, format_where
from apps.tickets.signing import event_key_b64

from . import badges, services
from .models import Direction


def _scan_org_ids(user) -> list[int]:
    return [
        m.organization_id
        for m in Membership.objects.filter(user=user, organization__is_active=True)
        if m.can(Perm.SCAN_TICKETS)
    ]


def _load_event(request, slug) -> tuple[Event, Membership]:
    event = get_object_or_404(Event.objects.select_related("venue", "organization"), slug=slug)
    membership = Membership.objects.filter(user=request.user, organization=event.organization).first()
    if membership is None or not membership.can(Perm.SCAN_TICKETS):
        raise PermissionDenied("You're not on the scanning team for this event.")
    return event, membership


def _event_info(ev) -> dict:
    return {
        "slug": ev.slug, "title": ev.title, "start_at": ev.start_at, "end_at": ev.end_at,
        "when": format_when(ev), "where": format_where(ev), "status": ev.status,
        "organization": ev.organization.name,
        **services.reentry_policy(ev),
        "badges_enabled": ev.badges_enabled,
    }


class ScanEventsView(APIView):
    """Events the signed-in user can scan: from 12 hours ago onwards."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        events = (
            Event.objects.filter(
                organization_id__in=_scan_org_ids(request.user),
                status__in=[EventStatus.PUBLISHED, EventStatus.CANCELLED],
                end_at__gte=timezone.now() - timedelta(hours=12),
            )
            .select_related("venue", "organization")
            .order_by("start_at")
        )
        return Response([{**_event_info(ev), "stats": services.event_stats(ev)} for ev in events])


class ManifestView(APIView):
    """
    Everything a scanner needs to work offline: the event's signing key (to
    reject forged QR codes) and its ticket list. Pass ?since=<server_time from
    the previous call> to receive only tickets changed since then.
    """

    @extend_schema(parameters=[OpenApiParameter("since", OpenApiTypes.DATETIME)], responses=OpenApiTypes.OBJECT)
    def get(self, request, slug):
        event, _ = _load_event(request, slug)
        server_time = timezone.now()
        qs = Ticket.objects.filter(event=event).select_related("ticket_type", "order").order_by("id")
        since = request.query_params.get("since")
        full = True
        if since:
            parsed = serializers.DateTimeField().to_internal_value(since)
            # Overlap a little so nothing changed during the previous request is missed.
            qs = qs.filter(updated_at__gte=parsed - timedelta(seconds=5))
            full = False
        return Response({
            "event": _event_info(event),
            "key": event_key_b64(event.pk),
            "server_time": server_time,
            "full": full,
            "tickets": [services.ticket_row(t) for t in qs],
            "stats": services.event_stats(event),
        })


class ScanSerializer(serializers.Serializer):
    raw = serializers.CharField(max_length=120, help_text="QR contents or a typed ticket code")
    gate = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    device_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    scanned_at = serializers.DateTimeField(required=False, allow_null=True)
    direction = serializers.ChoiceField(choices=Direction.choices, default=Direction.IN)
    count = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=50,
                                     help_text="People on a group ticket entering/leaving now (default: all)")


class ScanView(APIView):
    """Check one ticket in (online scanning)."""

    @extend_schema(request=ScanSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, slug):
        event, _ = _load_event(request, slug)
        ser = ScanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        result = services.check_in(event, d["raw"], user=request.user, gate=d["gate"],
                                   device_id=d["device_id"], scanned_at=d.get("scanned_at"),
                                   direction=d["direction"], count=d.get("count"))
        return Response({**result, "stats": services.event_stats(event)})


class OfflineScanSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=64)
    raw = serializers.CharField(max_length=120)
    gate = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    scanned_at = serializers.DateTimeField()
    direction = serializers.ChoiceField(choices=Direction.choices, default=Direction.IN)
    count = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=50)


class SyncSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    scans = OfflineScanSerializer(many=True, max_length=500)


class SyncView(APIView):
    """Upload scans made while offline. Each gets the server's verdict (e.g. duplicate)."""

    @extend_schema(request=SyncSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, slug):
        event, _ = _load_event(request, slug)
        ser = SyncSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        results = services.sync_scans(event, ser.validated_data["scans"], user=request.user,
                                      device_id=ser.validated_data["device_id"])
        return Response({"results": results, "stats": services.event_stats(event)})


class UndoSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12)


class UndoView(APIView):
    """Reverse a mistaken admission."""

    @extend_schema(request=UndoSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, slug):
        event, membership = _load_event(request, slug)
        ser = UndoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            ticket = services.undo_check_in(event, ser.validated_data["code"], user=request.user,
                                            can_manage=membership.can(Perm.MANAGE_EVENTS))
        except services.UndoError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response({"ticket": services.ticket_row(ticket), "stats": services.event_stats(event)})


# --------------------------------------------------------------------------
# Badge desk: phones admit at the door; the desk laptop sees them within
# seconds in "ready" and prints their badges.
# --------------------------------------------------------------------------
class BadgeEditSerializer(serializers.Serializer):
    attendee_name = serializers.CharField(max_length=150, required=False)
    attendee_organization = serializers.CharField(max_length=120, required=False, allow_blank=True)
    attendee_job_title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    badge_role = serializers.CharField(max_length=40, required=False, allow_blank=True)


def _badge_ticket(event, code):
    return get_object_or_404(
        Ticket.objects.select_related("ticket_type", "order", "event"), event=event, code=code.upper()
    )


class BadgeListView(APIView):
    """
    ?status=ready   admitted, badge not printed yet (oldest first): the print queue
    ?status=printed recently printed (for reprints)
    ?q=             search anyone with a ticket by name, organization or code (pre-printing)
    """

    @extend_schema(parameters=[OpenApiParameter("status", str, enum=["ready", "printed"]), OpenApiParameter("q", str)],
                   responses=OpenApiTypes.OBJECT)
    def get(self, request, slug):
        event, _ = _load_event(request, slug)
        qs = Ticket.objects.filter(event=event).exclude(status="void").select_related("ticket_type", "order", "event")
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(code__iexact=q) | Q(attendee_name__icontains=q) | Q(order__buyer_name__icontains=q)
                           | Q(attendee_organization__icontains=q)).order_by("attendee_name")[:30]
        elif request.query_params.get("status") == "printed":
            qs = qs.filter(badge_printed_at__isnull=False).order_by("-badge_printed_at")[:50]
        else:
            qs = qs.filter(admitted__gt=0, badge_printed_at__isnull=True).order_by("checked_in_at", "id")[:100]
        return Response({
            "event": {"title": event.title, "code": event.badge_event_code, "badges_enabled": event.badges_enabled,
                      "width_mm": event.badge_width_mm, "height_mm": event.badge_height_mm},
            "badges": [badges.badge_data(t) for t in qs],
            "stats": services.event_stats(event),
        })


class BadgeDetailView(APIView):
    """Correct a badge before printing. Changing the role needs event-manager rights."""

    @extend_schema(request=BadgeEditSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, slug, code):
        event, membership = _load_event(request, slug)
        ticket = _badge_ticket(event, code)
        ser = BadgeEditSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "badge_role" in data and not membership.can(Perm.MANAGE_EVENTS):
            raise PermissionDenied("Only event managers can change badge roles.")
        for field, value in data.items():
            setattr(ticket, field, value.strip())
        ticket.save(update_fields=[*data.keys(), "updated_at"])
        return Response(badges.badge_data(ticket))


class BadgePrintedView(APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, slug, code):
        event, _ = _load_event(request, slug)
        ticket = _badge_ticket(event, code)
        ticket.badge_printed_at = timezone.now()
        ticket.badge_print_count += 1
        ticket.save(update_fields=["badge_printed_at", "badge_print_count", "updated_at"])
        return Response(badges.badge_data(ticket))
