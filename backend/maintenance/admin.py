from django.contrib import admin

from assets.access import SiteScopedAdminMixin

from .models import PMSchedule, PMScheduleGeneration


class PMScheduleGenerationInline(admin.TabularInline):
    model = PMScheduleGeneration
    extra = 0
    fields = ("work_order", "due_date_at_generation", "generated_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PMSchedule)
class PMScheduleAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "asset__terminal__site_id"
    list_display = ("title", "asset", "interval_days", "next_due_date", "priority", "is_active")
    list_filter = ("is_active", "priority")
    search_fields = ("title", "asset__tag")
    readonly_fields = ("last_generated_work_order",)
    inlines = [PMScheduleGenerationInline]
