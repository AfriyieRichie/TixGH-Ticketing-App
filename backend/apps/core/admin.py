from django.contrib import admin

from .models import PlatformSettings


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Ticket fees",
            {
                "fields": ("fee_percent", "fee_flat", "fee_cap", "default_fee_bearer", "currency"),
                "description": "Charged on paid tickets only. The payment gateway "
                "charge is covered from this fee.",
            },
        ),
        ("Support contacts", {"fields": ("support_email", "support_phone")}),
    )
    readonly_fields = ("currency",)

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
