"""Organizer event management, mounted at /api/v1/organizations/<org_slug>/."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import dashboard, views

router = SimpleRouter()
router.register("venues", views.VenueViewSet, basename="venue")
router.register("events", views.EventViewSet, basename="org-event")

children = SimpleRouter()
children.register("ticket-types", views.TicketTypeViewSet, basename="ticket-type")
children.register("promo-codes", views.PromoCodeViewSet, basename="promo-code")

urlpatterns = [
    path("overview/", dashboard.OrganizationOverviewView.as_view(), name="org-overview"),
    path("events/<slug:event_slug>/stats/", dashboard.EventStatsView.as_view(), name="event-stats"),
    path("events/<slug:event_slug>/attendees/", dashboard.AttendeeListView.as_view(), name="event-attendees"),
    path("events/<slug:event_slug>/", include(children.urls)),
    path("", include(router.urls)),
]
