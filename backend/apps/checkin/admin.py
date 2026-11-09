from django.contrib import admin

from .models import CheckIn


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ("scanned_at", "event", "raw", "result", "gate", "scanned_by", "undone_at")
    list_filter = ("result", "gate")
    search_fields = ("raw", "event__title", "ticket__code")
    readonly_fields = [f.name for f in CheckIn._meta.fields]

    def has_add_permission(self, request):
        return False
