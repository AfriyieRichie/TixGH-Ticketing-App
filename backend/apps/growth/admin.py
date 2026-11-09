from django.contrib import admin

from .models import Campaign, Follow, Review, TrackingLink, Unsubscribe


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("event", "rating", "user", "is_hidden", "created_at")
    list_filter = ("rating", "is_hidden")
    search_fields = ("comment", "event__title", "user__email")
    list_editable = ("is_hidden",)  # hide abusive reviews


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("subject", "organization", "audience", "status", "automatic", "recipients_count", "sent_count",
                    "failed_count", "created_at")
    list_filter = ("status", "automatic")
    search_fields = ("subject", "organization__name")
    readonly_fields = ("recipients_count", "sent_count", "failed_count", "queued_at", "finished_at")


@admin.register(TrackingLink)
class TrackingLinkAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "event", "clicks", "commission_percent", "is_active")
    search_fields = ("code", "label", "event__title")


admin.site.register(Follow)
admin.site.register(Unsubscribe)
