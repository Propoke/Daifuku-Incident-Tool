from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .access import SiteScopedAdminMixin
from .models import (
    Asset,
    AssetConfigurationAssignment,
    ConfigurationTemplate,
    ConfigurationVersion,
    ConfigurationVersionItem,
    Customer,
    CustomerContact,
    CustomerSite,
    Item,
    ServiceContract,
    Site,
    SparePart,
    Terminal,
)


@admin.register(Site)
class SiteAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "id"
    list_display = ("name", "code")
    search_fields = ("name", "code")
    filter_horizontal = ("allowed_users", "allowed_groups")


@admin.register(Terminal)
class TerminalAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "site_id"
    list_display = ("code", "site")
    list_filter = ("site",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(CustomerContact)
class CustomerContactAdmin(admin.ModelAdmin):
    list_display = ("user", "customer", "phone")
    list_filter = ("customer",)
    autocomplete_fields = ("user",)


@admin.register(CustomerSite)
class CustomerSiteAdmin(admin.ModelAdmin):
    list_display = ("name", "customer")
    list_filter = ("customer",)


@admin.register(ServiceContract)
class ServiceContractAdmin(admin.ModelAdmin):
    list_display = ("name", "customer", "start_date", "end_date")
    list_filter = ("customer",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)


@admin.register(SparePart)
class SparePartAdmin(admin.ModelAdmin):
    list_display = ("sku", "barcode", "description", "supplier", "unit_cost", "is_active")
    filter_horizontal = ("items",)
    search_fields = ("sku", "barcode", "description")


class SuperuserOnlyEditMixin:
    """The configuration assigned to an asset - templates, versions, their
    items, and the assignment linking a version to an asset - can only be
    edited by an actual Django superuser, never by group/permission grants
    alone. Enforced here in code so it can't be loosened by mis-configuring
    a role's permissions; view access still follows the normal view_*
    permission for whoever has it."""

    def has_add_permission(self, request, obj=None):
        # obj is unused (ModelAdmin doesn't pass it, InlineModelAdmin does -
        # accept both call signatures).
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(ConfigurationTemplate)
class ConfigurationTemplateAdmin(SuperuserOnlyEditMixin, admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


class ConfigurationVersionItemInline(SuperuserOnlyEditMixin, admin.TabularInline):
    model = ConfigurationVersionItem
    extra = 1


@admin.register(ConfigurationVersion)
class ConfigurationVersionAdmin(SuperuserOnlyEditMixin, admin.ModelAdmin):
    list_display = ("__str__", "template", "version_label", "effective_date")
    list_filter = ("template",)
    inlines = [ConfigurationVersionItemInline]

    def get_readonly_fields(self, request, obj=None):
        # Enforce immutability in the admin UI too, once a version exists.
        if obj is not None:
            return [f.name for f in self.model._meta.fields]
        return []


class AssetConfigurationAssignmentInline(SuperuserOnlyEditMixin, admin.TabularInline):
    model = AssetConfigurationAssignment
    extra = 0
    fields = ("configuration_version", "effective_date", "notes", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Asset)
class AssetAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    # terminal is required for every asset regardless of ownership, so
    # site-scoping applies uniformly - see assets/access.py.
    site_lookup = "terminal__site_id"
    list_display = ("tag", "name", "owner_customer", "terminal", "status", "criticality")
    list_filter = ("owner_customer", "status", "criticality")
    search_fields = ("tag", "name", "serial_number")
    readonly_fields = ("history_link",)
    inlines = [AssetConfigurationAssignmentInline]

    @admin.display(description="History")
    def history_link(self, obj):
        if obj.pk is None:
            return "-"
        url = reverse("asset-history", args=[obj.pk])
        return format_html('<a href="{}">Tickets, configuration, permits, incidents, and changes</a>', url)


@admin.register(AssetConfigurationAssignment)
class AssetConfigurationAssignmentAdmin(SuperuserOnlyEditMixin, admin.ModelAdmin):
    list_display = ("asset", "configuration_version", "effective_date", "created_at")
    list_filter = ("asset",)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return [f.name for f in self.model._meta.fields]
        return []
