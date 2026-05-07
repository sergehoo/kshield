from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import APIKey, LoginAttempt, Role, RoleAssignment, RolePermission, User, UserSession


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "tenant", "company", "is_active", "mfa_enabled")
    list_filter = ("is_active", "is_staff", "tenant", "mfa_enabled")
    search_fields = ("email", "first_name", "last_name", "phone")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "phone", "photo")}),
        ("Organisation", {"fields": ("tenant", "company")}),
        ("Sécurité", {"fields": ("mfa_enabled", "mfa_secret", "failed_login_count", "locked_until", "last_ip")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "first_name", "last_name")}),
    )


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 1


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "scope", "is_system")
    list_filter = ("scope", "is_system")
    inlines = [RolePermissionInline]


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "site", "granted_at")
    list_filter = ("role",)
    search_fields = ("user__email",)


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "tenant", "site", "public_id", "is_active", "last_used_at")
    list_filter = ("scope", "is_active", "tenant")
    search_fields = ("name", "public_id")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("email", "ip", "success", "created_at")
    list_filter = ("success",)
    search_fields = ("email", "ip")


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "ip", "started_at", "last_activity_at", "revoked_at")
