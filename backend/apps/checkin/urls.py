"""Gate scanning API, mounted at /api/v1/scanner/."""

from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.ScanEventsView.as_view(), name="scan-events"),
    path("events/<slug:slug>/manifest/", views.ManifestView.as_view(), name="scan-manifest"),
    path("events/<slug:slug>/scan/", views.ScanView.as_view(), name="scan"),
    path("events/<slug:slug>/sync/", views.SyncView.as_view(), name="scan-sync"),
    path("events/<slug:slug>/undo/", views.UndoView.as_view(), name="scan-undo"),
    path("events/<slug:slug>/badges/", views.BadgeListView.as_view(), name="badge-list"),
    path("events/<slug:slug>/badges/<str:code>/", views.BadgeDetailView.as_view(), name="badge-detail"),
    path("events/<slug:slug>/badges/<str:code>/printed/", views.BadgePrintedView.as_view(), name="badge-printed"),
]
