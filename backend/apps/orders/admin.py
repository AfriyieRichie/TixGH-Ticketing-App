from django.contrib import admin

from apps.payments.models import Payment

from .models import Order, OrderItem, Ticket


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.fields


class OrderItemInline(ReadOnlyInline):
    model = OrderItem
    fields = ("ticket_type", "quantity", "unit_list_price", "unit_price", "unit_fee", "unit_buyer_pays")


class PaymentInline(ReadOnlyInline):
    model = Payment
    fields = ("reference", "gateway", "amount", "amount_paid", "status", "channel", "paid_at", "created_at")


class TicketInline(ReadOnlyInline):
    model = Ticket
    fields = ("code", "ticket_type", "attendee_name", "status", "checked_in_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "event", "buyer_name", "buyer_phone", "total", "status", "created_at")
    list_filter = ("status", "fee_bearer", "created_at")
    search_fields = ("reference", "buyer_name", "buyer_email", "buyer_phone", "event__title")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline, PaymentInline, TicketInline]
    readonly_fields = (
        "reference", "event", "user", "buyer_name", "buyer_email", "buyer_phone", "promo_code",
        "fee_bearer", "subtotal", "discount_total", "fee_total", "total", "organizer_amount",
        "platform_amount", "currency", "expires_at", "paid_at", "created_at", "updated_at",
    )
    fields = readonly_fields[:4] + ("status", "review_note") + readonly_fields[4:]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("event")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("code", "event", "ticket_type", "attendee_name", "status", "checked_in_at")
    list_filter = ("status",)
    search_fields = ("code", "attendee_name", "order__reference", "order__buyer_phone")
    readonly_fields = ("code", "order", "order_item", "event", "ticket_type", "holder", "issued_at")

    def has_add_permission(self, request):
        return False
