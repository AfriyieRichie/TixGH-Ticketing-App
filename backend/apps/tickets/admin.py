from django.contrib import admin

from .models import TicketTransfer


@admin.register(TicketTransfer)
class TicketTransferAdmin(admin.ModelAdmin):
    list_display = ("created_at", "old_code", "new_code", "from_user", "to_name", "to_contact")
    search_fields = ("old_code", "new_code", "to_contact", "to_name")
    readonly_fields = [f.name for f in TicketTransfer._meta.fields]

    def has_add_permission(self, request):
        return False
