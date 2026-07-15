from django.contrib import admin

from assets.access import SiteScopedAdminMixin

from .models import IncidentReport, PermitToWork


@admin.register(PermitToWork)
class PermitToWorkAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "asset__terminal__site_id"
    list_display = ("title", "asset", "status", "lockout_tagout_applied", "issued_to", "valid_from", "valid_until")
    list_filter = ("status", "lockout_tagout_applied")
    search_fields = ("title", "asset__tag")


@admin.register(IncidentReport)
class IncidentReportAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "site_id"
    list_display = ("__str__", "severity", "status", "asset", "reported_by", "occurred_at")
    list_filter = ("severity", "status", "site")
    search_fields = ("description", "asset__tag")
