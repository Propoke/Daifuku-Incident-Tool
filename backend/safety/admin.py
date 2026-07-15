from django.contrib import admin
from django.db.models import Q
from django.utils import timezone

from assets.access import SiteScopedAdminMixin
from core.admin import AttachmentInline, SetsAttachmentUploaderMixin
from teams.models import Certification

from .models import IncidentReport, PermitToWork

# Certification.name isn't a fixed enum (shops vary what they call
# things), so this check needs an exact string to match against - a
# technician's cert must be named exactly this for the warning below to
# recognize it.
LOTO_CERTIFICATION_NAME = "LOTO Authorized"


@admin.register(PermitToWork)
class PermitToWorkAdmin(SetsAttachmentUploaderMixin, SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "asset__terminal__site_id"
    list_display = ("title", "asset", "status", "lockout_tagout_applied", "issued_to", "valid_from", "valid_until")
    list_filter = ("status", "lockout_tagout_applied")
    search_fields = ("title", "asset__tag")
    inlines = [AttachmentInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.lockout_tagout_applied and obj.issued_to_id:
            has_current_cert = Certification.objects.filter(
                holder_id=obj.issued_to_id, name=LOTO_CERTIFICATION_NAME
            ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate())).exists()
            if not has_current_cert:
                self.message_user(
                    request,
                    f"{obj.issued_to} does not have a current \"{LOTO_CERTIFICATION_NAME}\" certification on "
                    "file. This permit was still issued - verify qualification before work begins.",
                    level="WARNING",
                )


@admin.register(IncidentReport)
class IncidentReportAdmin(SetsAttachmentUploaderMixin, SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "site_id"
    list_display = ("__str__", "severity", "status", "asset", "reported_by", "occurred_at")
    list_filter = ("severity", "status", "site")
    search_fields = ("description", "asset__tag")
    inlines = [AttachmentInline]
