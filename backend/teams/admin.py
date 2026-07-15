from django.contrib import admin

from assets.access import SiteScopedAdminMixin

from .models import Shift, ShiftHandoverNote, Team


@admin.register(Team)
class TeamAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "site_id"
    list_display = ("code", "name", "site", "lead")
    list_filter = ("site",)
    search_fields = ("code", "name")
    filter_horizontal = ("members",)


@admin.register(Shift)
class ShiftAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "team__site_id"
    list_display = ("name", "team", "start_time", "end_time", "days_of_week")
    list_filter = ("team",)


@admin.register(ShiftHandoverNote)
class ShiftHandoverNoteAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "team__site_id"
    list_display = ("team", "shift", "created_by", "created_at")
    list_filter = ("team",)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return [f.name for f in self.model._meta.fields]
        return []
