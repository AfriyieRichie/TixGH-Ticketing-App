from django.contrib import admin, messages

from .models import Payment, Refund, RefundStatus
from .refunds import process_refund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "order", "gateway", "amount", "status", "channel", "paid_at", "created_at")
    list_filter = ("status", "gateway", "channel")
    search_fields = ("reference", "order__reference")
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("order", "kind", "amount", "organizer_amount", "platform_amount", "status", "attempts", "created_at")
    list_filter = ("status", "kind")
    search_fields = ("order__reference", "order__buyer_name", "gateway_reference")
    readonly_fields = [f.name for f in Refund._meta.fields]
    actions = ["retry"]

    @admin.action(description="Retry failed refunds")
    def retry(self, request, queryset):
        done = 0
        for r in queryset.filter(status=RefundStatus.FAILED):
            r.status, r.attempts = RefundStatus.PENDING, 0
            r.save(update_fields=["status", "attempts"])
            done += process_refund(r).status != RefundStatus.FAILED
        self.message_user(request, f"Retried; {done} refund(s) now on their way.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
