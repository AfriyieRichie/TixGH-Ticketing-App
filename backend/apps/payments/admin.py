from django.contrib import admin

from .models import Payment


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
