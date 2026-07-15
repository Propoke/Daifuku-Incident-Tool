from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline

from .models import Attachment, ChecklistItem, ChecklistTemplate


class AttachmentInline(GenericTabularInline):
    """Drop this into any ModelAdmin's `inlines` to get a file-attachment
    section on that model's change page - already used on Asset, WorkOrder,
    PermitToWork, and IncidentReport.

    Setting `uploaded_by` automatically can't be done here: Django calls
    `save_new` on the formset instance, not on this InlineModelAdmin class,
    so any override placed here is dead code. See SetsAttachmentUploaderMixin
    below, which the parent ModelAdmin must also mix in."""

    model = Attachment
    extra = 1
    fields = ("file", "caption", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_by", "uploaded_at")


class SetsAttachmentUploaderMixin:
    """Mix into any ModelAdmin that includes AttachmentInline, so uploads
    made through it get uploaded_by set automatically. save_new() can't be
    overridden on the inline itself - Django calls it on the formset
    instance, not the InlineModelAdmin - so this has to live on the parent
    ModelAdmin's save_formset() hook instead."""

    def save_formset(self, request, form, formset, change):
        if formset.model is Attachment:
            instances = formset.save(commit=False)
            for instance in instances:
                if instance.uploaded_by_id is None:
                    instance.uploaded_by = request.user
                instance.save()
            formset.save_m2m()
            for obj in formset.deleted_objects:
                obj.delete()
        else:
            super().save_formset(request, form, formset, change)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "content_type", "object_id", "uploaded_by", "uploaded_at")
    list_filter = ("content_type",)
    readonly_fields = ("uploaded_by", "uploaded_at")


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 1
    fields = ("order", "text", "response_type")


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    inlines = [ChecklistItemInline]
