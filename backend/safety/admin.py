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
    list_display = (
        "title",
        "asset",
        "status",
        "lockout_tagout_applied",
        "issued_to",
        "approved_by",
        "valid_from",
        "valid_until",
    )
    list_filter = ("status", "lockout_tagout_applied")
    search_fields = ("title", "asset__tag")
    # approved_by/approved_at are never a plain form field - see the
    # "Approve selected permits" action below, gated on
    # can_approve_permittowork, which is the only way to set them.
    readonly_fields = ("approved_by", "approved_at")
    actions = ["approve_permits"]
    inlines = [AttachmentInline]

    @admin.action(description="Approve selected permits")
    def approve_permits(self, request, queryset):
        if not request.user.has_perm("safety.can_approve_permittowork"):
            self.message_user(
                request, "You don't have permission to approve permits to work.", level="ERROR"
            )
            return
        already_approved = queryset.filter(approved_by__isnull=False).count()
        to_approve = queryset.filter(approved_by__isnull=True)
        approved_count = to_approve.update(approved_by=request.user, approved_at=timezone.now())
        if approved_count:
            self.message_user(request, f"Approved {approved_count} permit(s).")
        if already_approved:
            self.message_user(
                request, f"{already_approved} permit(s) were already approved - left unchanged.", level="WARNING"
            )

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
