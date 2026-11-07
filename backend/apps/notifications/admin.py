from django.contrib import admin

from .models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "channel", "to", "status", "order")
    list_filter = ("status", "channel", "kind")
    search_fields = ("to", "order__reference")
    readonly_fields = [f.name for f in Delivery._meta.fields]

    def has_add_permission(self, request):
        return False
