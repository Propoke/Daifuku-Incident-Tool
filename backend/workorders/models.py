from django.conf import settings
from django.db import models
from django.utils import timezone

from assets.models import Asset, AssetConfigurationAssignment, ImmutableModel, SparePart
from core.models import ChecklistItem, ChecklistTemplate
from core.notifications import notify_work_order_assigned


class FailureCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return self.code


class WorkOrder(models.Model):
    class Type(models.TextChoices):
        CORRECTIVE = "CORRECTIVE", "Corrective"
        PREVENTIVE = "PREVENTIVE", "Preventive"
        PREDICTIVE = "PREDICTIVE", "Predictive"
        INSPECTION = "INSPECTION", "Inspection"
        PROJECT = "PROJECT", "Project"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        ON_HOLD = "ON_HOLD", "On hold"
        COMPLETED = "COMPLETED", "Completed"
        CLOSED = "CLOSED", "Closed"

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="work_orders")
    work_order_type = models.CharField(max_length=20, choices=Type.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    symptoms = models.TextField(blank=True, help_text="What was observed")
    cause = models.TextField(blank=True, help_text="Root cause, once known")
    resolution = models.TextField(blank=True, help_text="How it was resolved")

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reported_work_orders",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_work_orders",
    )
    # Can be set with or without assigned_to - a ticket can sit with a
    # team's queue before/instead of being handed to one individual.
    assigned_team = models.ForeignKey(
        "teams.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="work_orders"
    )

    # Snapshotted from Asset.current_configuration_assignment at creation
    # time and never changed afterward, so "what was this asset running
    # when we worked on it" stays answerable even after later
    # reconfigurations (feature draft, "work order tied to the asset's
    # configuration state at time of work").
    configuration_snapshot = models.ForeignKey(
        AssetConfigurationAssignment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="work_orders",
    )

    # Copied from PMSchedule.checklist_template when this work order is a
    # PM auto-generation (maintenance.services.generate_due_work_orders),
    # or set manually for a corrective ticket that warrants a formal
    # procedure. Optional - most corrective work orders won't have one.
    # What was actually filled out lives in WorkOrderChecklistResponse
    # below, not here.
    checklist_template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_orders"
    )

    failure_code = models.ForeignKey(
        FailureCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_orders"
    )

    due_date = models.DateField(null=True, blank=True)
    # The planned appointment/visit slot - distinct from due_date (a
    # deadline) and actual_open_time/actual_close_time (what really
    # happened). This is what the dispatch board (teams.services) schedules
    # against.
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Editable by an admin (unlike created_at/closed_at above, which are
    # system-managed record timestamps). These represent when the incident
    # actually started/was resolved in reality, which can differ from when
    # the record was created/closed in the system - e.g. an incident
    # reported by phone and logged later. Auto-populated with "now" if left
    # blank on save; an explicitly-set value is never overwritten.
    actual_open_time = models.DateTimeField(null=True, blank=True)
    actual_close_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"WO-{self.pk}: {self.title}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        previous_status = None
        previous_assigned_to_id = None
        previous_assigned_team_id = None
        if not is_new:
            previous = (
                WorkOrder.objects.filter(pk=self.pk)
                .values("status", "assigned_to_id", "assigned_team_id")
                .first()
            )
            if previous:
                previous_status = previous["status"]
                previous_assigned_to_id = previous["assigned_to_id"]
                previous_assigned_team_id = previous["assigned_team_id"]

        if is_new and self.configuration_snapshot_id is None:
            self.configuration_snapshot = self.asset.current_configuration_assignment

        if self.actual_open_time is None:
            self.actual_open_time = timezone.now()

        if self.status == self.Status.CLOSED:
            if self.closed_at is None:
                self.closed_at = timezone.now()
            if self.actual_close_time is None:
                self.actual_close_time = timezone.now()

        super().save(*args, **kwargs)

        if is_new or previous_status != self.status:
            WorkOrderStatusChange.objects.create(
                work_order=self,
                from_status=previous_status or "",
                to_status=self.status,
            )

        assignment_changed = is_new or (
            previous_assigned_to_id != self.assigned_to_id or previous_assigned_team_id != self.assigned_team_id
        )
        if assignment_changed and (self.assigned_to_id or self.assigned_team_id):
            notify_work_order_assigned(self)


class WorkOrderStatusChange(ImmutableModel):
    """Append-only log, auto-created by WorkOrder.save() on every status
    transition - not meant to be created/edited directly."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="status_changes")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.work_order} : {self.from_status or '(new)'} -> {self.to_status}"


class WorkOrderComment(ImmutableModel):
    """A running, chronological note thread on one specific work order -
    what a technician actually reaches for to leave a quick note for the
    next shift on *this ticket*. Distinct from teams.ShiftHandoverNote
    (a whole-shift handover, not tied to any one ticket) and from the
    single description/symptoms/cause/resolution fields on WorkOrder
    (a summary, not a thread). Append-only like WorkOrderStatusChange -
    editing/deleting a comment after the fact isn't how a shared work log
    should behave."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.work_order} by {self.author}"


class WorkOrderChecklistResponse(ImmutableModel):
    """What a technician actually entered for one ChecklistItem on one
    work order - the answer to "PM compliance measures the ticket got
    closed, but did the actual steps get done?". Append-only like the
    other work-order logs: if a step needs redoing (failed the first
    check, fixed it, re-checked), that's a new response row for the same
    item rather than editing the old one, so the full attempt history
    stays visible instead of being overwritten. Callers wanting "the
    current answer" per item should take the latest response per
    checklist_item (highest completed_at)."""

    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="checklist_responses")
    checklist_item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT, related_name="+")
    response_text = models.CharField(
        max_length=300, help_text="PASS/FAIL, a number, or free text, depending on the item's response_type"
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["completed_at"]

    def __str__(self):
        return f"{self.work_order} - {self.checklist_item.text}: {self.response_text}"


class WorkOrderLaborEntry(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="labor_entries")
    technician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="labor_entries")
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.work_order} - {self.technician} - {self.hours}h"


class WorkOrderPartUsage(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="part_usages")
    spare_part = models.ForeignKey(SparePart, on_delete=models.PROTECT, related_name="work_order_usages")
    quantity = models.PositiveIntegerField(default=1)
    date = models.DateField()
    # Nullable: historical/manually-entered usage may not specify exactly
    # where the part came from, but the barcode-scan flow
    # (inventory.services.consume_stock) always sets this.
    stock_location = models.ForeignKey(
        "inventory.StockLocation", on_delete=models.PROTECT, null=True, blank=True, related_name="part_usages"
    )

    def __str__(self):
        return f"{self.work_order} - {self.spare_part} x{self.quantity}"
