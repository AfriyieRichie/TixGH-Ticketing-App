"""Private ticket pages linked from SMS/email, mounted at /t/."""

from django.urls import path

from . import views

urlpatterns = [
    path("ticket/<str:code>/<str:token>/", views.single_ticket_page, name="ticket-page"),
    path("ticket/<str:code>/<str:token>/pdf/", views.single_ticket_pdf, name="ticket-page-pdf"),
    path("<str:reference>/<str:token>/", views.order_tickets_page, name="order-tickets-page"),
    path("<str:reference>/<str:token>/pdf/", views.order_tickets_pdf, name="order-tickets-pdf"),
]
