from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("config/", views.public_config, name="public-config"),
    path("internal/cron/", views.cron, name="cron"),
]
