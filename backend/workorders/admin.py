from django.contrib import admin

from assets.access import SiteScopedAdminMixin
from core.admin import AttachmentInline, SetsAttachmentUploaderMixin

from core.models import ChecklistItem

from .models import (
    FailureCode,
    WorkOrder,
    WorkOrderChecklistResponse,
    WorkOrderComment,
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


class WorkOrderCommentInline(admin.TabularInline):
    """Add-only, like the model itself (ImmutableModel) - existing
    comments can't be edited or deleted through this inline, only
    appended to."""

    model = WorkOrderComment
    extra = 1
    fields = ("body", "author", "created_at")
    readonly_fields = ("author", "created_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WorkOrderChecklistResponseInline(admin.TabularInline):
    """Add-only, like WorkOrderCommentInline - responses can't be edited
    or deleted here, only appended to (see WorkOrderChecklistResponse's
    ImmutableModel base). The checklist_item dropdown is restricted to
    items belonging to this work order's own checklist_template, not
    every ChecklistItem in the system."""

    model = WorkOrderChecklistResponse
    extra = 1
    fields = ("checklist_item", "response_text", "completed_by", "completed_at")
    readonly_fields = ("completed_by", "completed_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_formset(self, request, obj=None, **kwargs):
        self.parent_work_order = obj
        return super().get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "checklist_item":
            work_order = getattr(self, "parent_work_order", None)
            if work_order is not None and work_order.checklist_template_id:
                kwargs["queryset"] = ChecklistItem.objects.filter(template_id=work_order.checklist_template_id)
            else:
                kwargs["queryset"] = ChecklistItem.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class SetsWorkOrderCommentAuthorMixin:
    """Mix into WorkOrderAdmin so comments added through
    WorkOrderCommentInline get `author` set automatically. Same issue as
    core.admin.SetsAttachmentUploaderMixin: save_new() can't be overridden
    on the inline itself - Django calls it on the formset instance, not
    the InlineModelAdmin - so this uses the parent ModelAdmin's
    save_formset() hook instead."""

    def save_formset(self, request, form, formset, change):
        if formset.model is WorkOrderComment:
            instances = formset.save(commit=False)
            for instance in instances:
                if instance.author_id is None:
                    instance.author = request.user
                instance.save()
            formset.save_m2m()
            for obj in formset.deleted_objects:
                obj.delete()
        else:
            super().save_formset(request, form, formset, change)


class SetsWorkOrderChecklistResponseCompletedByMixin:
    """Same fix as SetsWorkOrderCommentAuthorMixin, for
    WorkOrderChecklistResponseInline's completed_by field."""

    def save_formset(self, request, form, formset, change):
        if formset.model is WorkOrderChecklistResponse:
            instances = formset.save(commit=False)
            for instance in instances:
                if instance.completed_by_id is None:
                    instance.completed_by = request.user
                instance.save()
            formset.save_m2m()
            for obj in formset.deleted_objects:
                obj.delete()
        else:
            super().save_formset(request, form, formset, change)


@admin.register(WorkOrder)
class WorkOrderAdmin(
    SetsWorkOrderChecklistResponseCompletedByMixin,
    SetsWorkOrderCommentAuthorMixin,
    SetsAttachmentUploaderMixin,
    SiteScopedAdminMixin,
    admin.ModelAdmin,
):
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
    inlines = [
        WorkOrderStatusChangeInline,
        WorkOrderCommentInline,
        WorkOrderChecklistResponseInline,
        WorkOrderLaborEntryInline,
        WorkOrderPartUsageInline,
        AttachmentInline,
    ]

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
