"""Public and user-facing growth endpoints (mounted under /api/v1/)."""

from django.urls import path

from . import views

urlpatterns = [
    path("organizations/public/<slug:slug>/follow/", views.FollowView.as_view(), name="follow"),
    path("me/following/", views.FollowingListView.as_view(), name="following"),
    path("events/<slug:slug>/ref/<str:code>/", views.RefClickView.as_view(), name="ref-click"),
    path("events/<slug:slug>/reviews/", views.EventReviewsView.as_view(), name="event-reviews"),
]
