from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Attachment(models.Model):
    """A file/photo attached to any model (Asset, WorkOrder, PermitToWork,
    IncidentReport, ...) via a generic relation, so this is one model
    instead of one per app. Deliberately not append-only like
    assets.models.ImmutableModel - the metadata is small enough that
    "delete and re-upload" isn't a real burden, and locking out deletion
    entirely would mean an accidental upload can never be removed. Kept
    mutable but delete permission is intentionally restricted (see
    core/migrations/0010_attachment_permissions.py) so it isn't "anyone
    can make evidence disappear".

    Storage is local disk (Django's default FileField) for now - the
    infra plan already flags object storage (MinIO) as the production
    answer for exactly this once real volume shows up; not wired up here
    since there's no MinIO instance to configure against yet.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    file = models.FileField(upload_to="attachments/%Y/%m/")
    caption = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return self.caption or self.file.name


class ChecklistTemplate(models.Model):
    """A reusable, ordered set of steps - "torque to spec", "inspect belt
    tension", "verify E-stop" - instead of the free-text paragraph
    PMSchedule.description and PermitToWork.description were limited to.
    Lives in core (not maintenance or safety) because both PMSchedule and
    PermitToWork reference the same template shape; a work order created
    from a PM schedule is where responses actually get recorded (see
    workorders.models.WorkOrderChecklistResponse)."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ChecklistItem(models.Model):
    class ResponseType(models.TextChoices):
        PASS_FAIL = "PASS_FAIL", "Pass/Fail"
        NUMERIC = "NUMERIC", "Numeric"
        TEXT = "TEXT", "Text"

    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveIntegerField(default=0)
    text = models.CharField(max_length=300)
    response_type = models.CharField(max_length=20, choices=ResponseType.choices, default=ResponseType.PASS_FAIL)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.template.name}: {self.text}"
