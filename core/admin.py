from django.contrib import admin

from .models import Address, Company, FeatureFlag, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "currency", "timezone", "is_active", "created_at")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "code")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tenant", "sector", "is_active")
    list_filter = ("sector", "is_active", "tenant")
    search_fields = ("name", "code", "legal_name", "tax_id")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("line1", "city", "region", "country")
    search_fields = ("line1", "city", "region")


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("code", "tenant", "is_enabled")
    list_filter = ("is_enabled", "tenant")
    search_fields = ("code",)
