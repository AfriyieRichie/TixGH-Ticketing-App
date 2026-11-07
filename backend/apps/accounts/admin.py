from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from apps.core.phone import InvalidPhoneNumber, normalize_phone

from .models import OTPCode, User


class UserForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        help_text="Passwords are not stored in plain text. Use the change-password form."
    )

    class Meta:
        model = User
        fields = "__all__"

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        if not phone:
            return None
        try:
            return normalize_phone(phone)
        except InvalidPhoneNumber as exc:
            raise forms.ValidationError(str(exc))

    def clean(self):
        data = super().clean()
        if not data.get("email") and not data.get("phone"):
            raise forms.ValidationError("Enter an email address or a phone number.")
        return data


class UserCreationForm(UserForm):
    password = None
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ("email", "phone", "full_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        else:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserForm
    add_form = UserCreationForm
    ordering = ("-date_joined",)
    list_display = ("__str__", "email", "phone", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "email_verified", "phone_verified")
    search_fields = ("full_name", "email", "phone")
    readonly_fields = ("date_joined", "last_login")
    fieldsets = (
        (None, {"fields": ("full_name", "email", "phone", "password")}),
        ("Verification", {"fields": ("email_verified", "phone_verified", "marketing_opt_in")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("full_name", "email", "phone", "password1")}),)


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("target", "purpose", "attempts", "created_at", "expires_at", "consumed_at")
    list_filter = ("purpose",)
    search_fields = ("target",)
    readonly_fields = [f.name for f in OTPCode._meta.fields]

    def has_add_permission(self, request):
        return False
