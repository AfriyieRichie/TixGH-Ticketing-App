from datetime import timedelta

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

from . import services
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
