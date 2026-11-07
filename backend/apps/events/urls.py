"""Public event discovery: /api/v1/events/, /api/v1/categories/."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("events", views.PublicEventViewSet, basename="public-event")

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("", include(router.urls)),
]
