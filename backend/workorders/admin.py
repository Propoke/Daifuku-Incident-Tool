from django.contrib import admin

from assets.access import SiteScopedAdminMixin
from core.admin import AttachmentInline, SetsAttachmentUploaderMixin

from .models import (
    FailureCode,
    WorkOrder,
    WorkOrderLaborEntry,
    WorkOrderPartUsage,
    WorkOrderStatusChange,
)
from .sla import get_sla_status


@admin.register(FailureCode)
class FailureCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description")


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WorkOrderStatusChangeInline(ReadOnlyInline):
    model = WorkOrderStatusChange
    fields = ("from_status", "to_status", "changed_by", "changed_at", "notes")
    readonly_fields = fields


class WorkOrderLaborEntryInline(admin.TabularInline):
    model = WorkOrderLaborEntry
    extra = 0


class WorkOrderPartUsageInline(admin.TabularInline):
    model = WorkOrderPartUsage
    extra = 0


@admin.register(WorkOrder)
class WorkOrderAdmin(SetsAttachmentUploaderMixin, SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "asset__terminal__site_id"
    list_display = (
        "__str__",
        "asset",
        "work_order_type",
        "priority",
        "status",
        "assigned_team",
        "assigned_to",
        "scheduled_start",
        "actual_open_time",
        "actual_close_time",
    )
    list_filter = ("status", "priority", "work_order_type")
    search_fields = ("title", "description", "symptoms", "cause", "resolution", "asset__tag")
    # actual_open_time/actual_close_time are intentionally editable (an admin
    # can correct them) - see the comment on those fields in models.py.
    # Auto-population only fills them in when left blank.
    readonly_fields = ("configuration_snapshot", "created_at", "updated_at", "closed_at", "sla_status")
    inlines = [WorkOrderStatusChangeInline, WorkOrderLaborEntryInline, WorkOrderPartUsageInline, AttachmentInline]

    @admin.display(description="SLA status")
    def sla_status(self, obj):
        status = get_sla_status(obj)
        if status is None:
            return "No SLA on this asset's contract"
        parts = []
        if "response" in status:
            r = status["response"]
            parts.append(f"Response: {r['status']} ({r['elapsed_hours']}h / {r['target_hours']}h target)")
        if "resolution" in status:
            r = status["resolution"]
            parts.append(f"Resolution: {r['status']} ({r['elapsed_hours']}h / {r['target_hours']}h target)")
        return " | ".join(parts)
