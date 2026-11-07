from django.contrib import admin, messages
from django.utils import timezone

from .models import Invitation, Membership, Organization, PayoutAccount, VerificationStatus


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)
    fk_name = "organization"
    readonly_fields = ("created_at",)
    fields = ("user", "role", "created_at")


class PayoutAccountInline(admin.StackedInline):
    model = PayoutAccount
    extra = 0
    fields = (
        ("method", "mobile_money_provider"),
        ("bank_name", "bank_code"),
        ("account_number", "account_name"),
        ("is_default", "is_verified"),
        "gateway_subaccount_code",
    )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "city", "verification_status", "is_active", "created_at")
    list_filter = ("verification_status", "is_active", "region")
    search_fields = ("name", "slug", "email", "phone")
    readonly_fields = ("slug", "verified_at", "created_by", "created_at", "updated_at")
    inlines = [MembershipInline, PayoutAccountInline]
    actions = ["approve_verification", "reject_verification"]
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "logo", "is_active")}),
        ("Contact", {"fields": ("email", "phone", "website", "region", "city")}),
        ("Social", {"fields": ("instagram", "x_handle", "facebook", "tiktok")}),
        ("Verification", {"fields": ("verification_status", "verification_note", "verified_at")}),
        (
            "Commercial terms",
            {
                "fields": ("fee_bearer", "fee_percent_override", "fee_flat_override"),
                "description": "Leave blank to use the platform defaults.",
            },
        ),
        ("Meta", {"fields": ("created_by", "created_at", "updated_at")}),
    )

    @admin.action(description="Approve verification (adds Verified badge)")
    def approve_verification(self, request, queryset):
        n = queryset.update(
            verification_status=VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
            verification_note="",
        )
        self.message_user(request, f"{n} organizer(s) verified.", messages.SUCCESS)

    @admin.action(description="Reject verification")
    def reject_verification(self, request, queryset):
        n = queryset.update(verification_status=VerificationStatus.REJECTED, verified_at=None)
        self.message_user(
            request,
            f"{n} organizer(s) rejected. Edit each one to add a note explaining why.",
            messages.WARNING,
        )


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("contact", "organization", "role", "status", "created_at")
    list_filter = ("role",)
    search_fields = ("contact", "organization__name")
    readonly_fields = ("token", "created_at", "accepted_at", "accepted_by")
