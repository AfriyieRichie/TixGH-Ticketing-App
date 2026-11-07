from django.urls import path

from . import views

urlpatterns = [
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("orders/", views.MyOrdersView.as_view(), name="my-orders"),
    path("orders/<str:reference>/", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:reference>/verify/", views.OrderVerifyView.as_view(), name="order-verify"),
    path("orders/<str:reference>/resend/", views.OrderResendView.as_view(), name="order-resend"),
    path("orders/<str:reference>/retry-payment/", views.OrderRetryPaymentView.as_view(), name="order-retry"),
]
