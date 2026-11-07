"""Wallet API, mounted at /api/v1/tickets/."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.WalletListView.as_view(), name="wallet"),
    path("<str:code>/", views.WalletTicketView.as_view(), name="wallet-ticket"),
    path("<str:code>/transfer/", views.TicketTransferView.as_view(), name="ticket-transfer"),
    path("<str:code>/pdf/", views.WalletTicketPdfView.as_view(), name="wallet-ticket-pdf"),
]
