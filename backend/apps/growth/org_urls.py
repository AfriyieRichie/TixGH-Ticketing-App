"""Organizer growth tools, mounted at /api/v1/organizations/<org_slug>/."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("campaigns", views.CampaignViewSet, basename="campaign")

links = SimpleRouter()
links.register("tracking-links", views.TrackingLinkViewSet, basename="tracking-link")

urlpatterns = [
    path("audience/", views.AudienceView.as_view(), name="audience"),
    path("events/<slug:event_slug>/reviews/<int:pk>/reply/", views.ReviewReplyView.as_view(), name="review-reply"),
    path("events/<slug:event_slug>/", include(links.urls)),
    path("", include(router.urls)),
]
