"""Organizer dashboard data: sales stats, attendee lists, CSV export."""

import csv
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order, OrderItem, OrderStatus, Ticket, TicketStatus
from apps.organizations.models import Perm
from apps.organizations.permissions import OrgScopedMixin

from .models import EventStatus

ZERO = Decimal("0.00")


def _money(v) -> str:
    return str((v or ZERO).quantize(Decimal("0.01")))


class _DashboardMixin(OrgScopedMixin):
    """Sales data is for people who run events or handle money."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not (self.membership.can(Perm.MANAGE_EVENTS) or self.membership.can(Perm.VIEW_FINANCE)):
            raise PermissionDenied("Your team role does not allow viewing sales.")
        if "event_slug" in kwargs:
            self.event = get_object_or_404(self.organization.events, slug=kwargs["event_slug"])


def _totals(orders) -> dict:
    agg = orders.aggregate(
        gross=Sum("total"), earnings=Sum("organizer_amount"), fees=Sum("fee_total"),
        discounts=Sum("discount_total"), orders=Count("id"),
    )
    return {
        "gross_sales": _money(agg["gross"]), "organizer_earnings": _money(agg["earnings"]),
        "booking_fees": _money(agg["fees"]), "discounts": _money(agg["discounts"]),
        "orders": agg["orders"],
    }


class OrganizationOverviewView(_DashboardMixin, APIView):
    """Headline numbers across all of the organizer's events."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_slug):
        org = self.organization
        paid = Order.objects.filter(event__organization=org, status=OrderStatus.PAID)
        now = timezone.now()
        events = org.events.all()
        recent = paid.select_related("event").order_by("-paid_at")[:10]
        top = (
            paid.values("event__slug", "event__title")
            .annotate(earnings=Sum("organizer_amount"), orders=Count("id"))
            .order_by("-earnings")[:5]
        )
        return Response({
            **_totals(paid),
            "tickets_sold": Ticket.objects.filter(event__organization=org).exclude(status=TicketStatus.VOID).count(),
            "events": {
                "upcoming": events.filter(status=EventStatus.PUBLISHED, end_at__gte=now).count(),
                "drafts": events.filter(status=EventStatus.DRAFT).count(),
                "past": events.filter(end_at__lt=now).exclude(status=EventStatus.DRAFT).count(),
            },
            "recent_orders": [
                {"reference": o.reference, "buyer_name": o.buyer_name, "event": o.event.title,
                 "total": _money(o.total), "earnings": _money(o.organizer_amount), "paid_at": o.paid_at}
                for o in recent
            ],
            "top_events": [
                {"slug": t["event__slug"], "title": t["event__title"], "earnings": _money(t["earnings"]),
                 "orders": t["orders"]}
                for t in top
            ],
            "needs_review": Order.objects.filter(event__organization=org, status=OrderStatus.NEEDS_REVIEW).count(),
        })


class EventStatsView(_DashboardMixin, APIView):
    """Sales for one event: totals, per ticket type, and daily sales (last 30 days)."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, org_slug, event_slug):
        ev = self.event
        paid = Order.objects.filter(event=ev, status=OrderStatus.PAID)
        per_type = []
        tickets = Ticket.objects.filter(event=ev)
        checked = dict(
            tickets.filter(status=TicketStatus.CHECKED_IN).values_list("ticket_type_id").annotate(n=Count("id"))
        )
        earnings_by_type: dict[int, Decimal] = {}
        for it in OrderItem.objects.filter(order__in=paid):
            earnings_by_type[it.ticket_type_id] = (
                earnings_by_type.get(it.ticket_type_id, ZERO) + it.unit_organizer_receives * it.quantity
            )
        for t in ev.ticket_types.all():
            per_type.append({
                "id": t.pk, "name": t.name, "price": _money(t.price), "quantity": t.quantity,
                "sold": t.quantity_sold, "available": t.quantity_available,
                "checked_in": checked.get(t.pk, 0), "earnings": _money(earnings_by_type.get(t.pk)),
                "sale_status": t.sale_status,
            })
        since = timezone.now() - timedelta(days=30)
        daily = (
            paid.filter(paid_at__gte=since)
            .annotate(day=TruncDate("paid_at", tzinfo=timezone.get_current_timezone()))
            .values("day")
            .annotate(orders=Count("id"), earnings=Sum("organizer_amount"))
            .order_by("day")
        )
        issued = tickets.exclude(status=TicketStatus.VOID)
        return Response({
            **_totals(paid),
            "tickets_sold": issued.count(),
            "checked_in": issued.filter(status=TicketStatus.CHECKED_IN).count(),
            "capacity": sum(t.quantity for t in ev.ticket_types.all()),
            "ticket_types": per_type,
            "daily": [{"date": d["day"], "orders": d["orders"], "earnings": _money(d["earnings"])} for d in daily],
            "pending_orders": Order.objects.filter(
                event=ev, status=OrderStatus.PENDING, expires_at__gt=timezone.now()
            ).count(),
        })


class AttendeeSerializer(serializers.ModelSerializer):
    ticket_type = serializers.CharField(source="ticket_type.name")
    order = serializers.CharField(source="order.reference")
    buyer_name = serializers.CharField(source="order.buyer_name")
    buyer_phone = serializers.CharField(source="order.buyer_phone")
    buyer_email = serializers.CharField(source="order.buyer_email")
    paid_at = serializers.DateTimeField(source="order.paid_at")

    class Meta:
        model = Ticket
        fields = [
            "code", "ticket_type", "attendee_name", "attendee_phone", "attendee_email", "status",
            "checked_in_at", "order", "buyer_name", "buyer_phone", "buyer_email", "paid_at",
        ]


CSV_COLUMNS = [
    ("Ticket code", "code"), ("Ticket type", "ticket_type"), ("Attendee", "attendee_name"),
    ("Buyer", "buyer_name"), ("Buyer phone", "buyer_phone"), ("Buyer email", "buyer_email"),
    ("Order", "order"), ("Paid at", "paid_at"), ("Status", "status"), ("Checked in at", "checked_in_at"),
]


class AttendeeListView(_DashboardMixin, ListAPIView):
    """Everyone holding a ticket. ?q= searches names, phones, codes. ?export=csv downloads."""

    serializer_class = AttendeeSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Ticket.objects.none()
        qs = Ticket.objects.filter(event=self.event).select_related("ticket_type", "order").order_by("id")
        p = self.request.query_params
        if q := p.get("q", "").strip():
            qs = qs.filter(
                Q(code__iexact=q) | Q(attendee_name__icontains=q) | Q(order__buyer_name__icontains=q)
                | Q(order__buyer_phone__icontains=q.lstrip("0")) | Q(order__buyer_email__icontains=q)
                | Q(order__reference__iexact=q)
            )
        if st := p.get("status"):
            qs = qs.filter(status=st)
        if tt := p.get("ticket_type"):
            qs = qs.filter(ticket_type_id=tt)
        return qs

    @extend_schema(parameters=[
        OpenApiParameter("q", str), OpenApiParameter("status", str, enum=["valid", "checked_in", "void"]),
        OpenApiParameter("ticket_type", int), OpenApiParameter("export", str, enum=["csv"]),
    ])
    def get(self, request, *args, **kwargs):
        if request.query_params.get("export") == "csv":
            resp = HttpResponse(content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="attendees-{self.event.slug}.csv"'
            resp.write("﻿")  # BOM so Excel opens UTF-8 names correctly
            writer = csv.writer(resp)
            writer.writerow([c for c, _ in CSV_COLUMNS])
            for row in AttendeeSerializer(self.get_queryset(), many=True).data:
                writer.writerow([row[f] or "" for _, f in CSV_COLUMNS])
            return resp
        return super().get(request, *args, **kwargs)
