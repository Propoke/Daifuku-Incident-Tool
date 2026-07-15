from django.contrib import admin

from assets.access import SiteScopedAdminMixin
from core.admin import AttachmentInline, SetsAttachmentUploaderMixin

from .models import IncidentReport, PermitToWork


@admin.register(PermitToWork)
class PermitToWorkAdmin(SetsAttachmentUploaderMixin, SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "asset__terminal__site_id"
    list_display = ("title", "asset", "status", "lockout_tagout_applied", "issued_to", "valid_from", "valid_until")
    list_filter = ("status", "lockout_tagout_applied")
    search_fields = ("title", "asset__tag")
    inlines = [AttachmentInline]


@admin.register(IncidentReport)
class IncidentReportAdmin(SetsAttachmentUploaderMixin, SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "site_id"
    list_display = ("__str__", "severity", "status", "asset", "reported_by", "occurred_at")
    list_filter = ("severity", "status", "site")
    search_fields = ("description", "asset__tag")
    inlines = [AttachmentInline]
