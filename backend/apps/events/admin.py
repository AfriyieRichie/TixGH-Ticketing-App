from django.contrib import admin, messages

from .models import Category, Event, PromoCode, TicketType, Venue


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "region", "organization", "capacity")
    list_filter = ("region",)
    search_fields = ("name", "city", "address", "organization__name")
    autocomplete_fields = ("organization",)


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 0
    fields = ("name", "price", "quantity", "quantity_sold", "admits", "visibility", "is_active", "sort_order")
    readonly_fields = ("quantity_sold",)


class PromoCodeInline(admin.TabularInline):
    model = PromoCode
    extra = 0
    fields = ("code", "discount_type", "amount", "max_uses", "times_used", "valid_until", "is_active")
    readonly_fields = ("times_used",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "start_at", "status", "visibility", "is_featured", "tickets_sold")
    list_filter = ("status", "visibility", "is_featured", "format", "category", "venue__region")
    search_fields = ("title", "slug", "organization__name", "venue__name", "venue__city")
    date_hierarchy = "start_at"
    autocomplete_fields = ("organization", "venue")
    readonly_fields = ("slug", "published_at", "cancelled_at", "created_by", "created_at", "updated_at")
    inlines = [TicketTypeInline, PromoCodeInline]
    actions = ["feature", "unfeature"]
    fieldsets = (
        (None, {"fields": ("organization", "title", "slug", "summary", "description", "category", "cover_image")}),
        ("When and where", {"fields": ("format", "venue", "online_url", "start_at", "end_at")}),
        ("Status", {"fields": ("status", "visibility", "is_featured", "published_at",
                               "cancelled_at", "cancellation_reason")}),
        ("Rules", {"fields": ("age_restriction", "max_tickets_per_order", "fee_bearer",
                              "refund_policy", "refund_policy_details")}),
        ("Meta", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("organization").prefetch_related("ticket_types")

    @admin.display(description="Sold")
    def tickets_sold(self, obj):
        return obj.tickets_sold

    @admin.action(description="Feature on homepage")
    def feature(self, request, queryset):
        n = queryset.update(is_featured=True)
        self.message_user(request, f"{n} event(s) featured.", messages.SUCCESS)

    @admin.action(description="Remove from homepage")
    def unfeature(self, request, queryset):
        n = queryset.update(is_featured=False)
        self.message_user(request, f"{n} event(s) un-featured.", messages.SUCCESS)
