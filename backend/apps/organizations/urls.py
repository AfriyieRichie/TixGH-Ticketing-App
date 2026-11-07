from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.OrganizationViewSet, basename="organization")

payouts = SimpleRouter()
payouts.register("payout-accounts", views.PayoutAccountViewSet, basename="payout-account")

urlpatterns = [
    # Must come before the router so "public"/"invitations" aren't read as slugs.
    path("public/<slug:slug>/", views.PublicOrganizationView.as_view(), name="organization-public"),
    path("invitations/<str:token>/", views.InvitationByTokenView.as_view(), name="invitation-token"),
    path("<slug:org_slug>/members/", views.MemberListView.as_view(), name="member-list"),
    path("<slug:org_slug>/members/<int:pk>/", views.MemberDetailView.as_view(), name="member-detail"),
    path("<slug:org_slug>/invitations/", views.InvitationListCreateView.as_view(), name="invitation-list"),
    path(
        "<slug:org_slug>/invitations/<int:pk>/",
        views.InvitationRevokeView.as_view(),
        name="invitation-revoke",
    ),
    path("<slug:org_slug>/", include(payouts.urls)),
    path("<slug:org_slug>/", include("apps.events.org_urls")),
    path("", include(router.urls)),
]
