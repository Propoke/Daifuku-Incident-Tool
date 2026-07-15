from django.contrib import admin

from .models import (
    FailureCode,
    WorkOrder,
    WorkOrderLaborEntry,
    WorkOrderPartUsage,
    WorkOrderStatusChange,
)


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
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "asset", "work_order_type", "priority", "status", "assigned_to", "due_date")
    list_filter = ("status", "priority", "work_order_type")
    search_fields = ("title", "description", "asset__tag")
    readonly_fields = ("configuration_snapshot", "created_at", "updated_at", "closed_at")
    inlines = [WorkOrderStatusChangeInline, WorkOrderLaborEntryInline, WorkOrderPartUsageInline]
