from django.urls import path

from . import views

urlpatterns = [
    path("banks/", views.BankListView.as_view(), name="bank-list"),
    path("webhook/paystack/", views.PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("simulated/<str:reference>/", views.simulated_checkout, name="payment-simulated"),
]
