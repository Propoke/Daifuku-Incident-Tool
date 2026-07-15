from django.db import models

from assets.models import Asset, ImmutableModel
from core.models import ChecklistTemplate
from workorders.models import WorkOrder


class PMSchedule(models.Model):
    """A recurring preventive-maintenance trigger for one asset.

    First cut is time-based only (a fixed day interval from a start date).
    Usage/meter-based triggers (runtime hours, cycle counts) are explicitly
    future scope per the feature draft - they depend on equipment actually
    reporting meter readings, which nothing in this system does yet.
    """

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="pm_schedules")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Free-text procedure notes for the generated work order")
    # Structured steps (torque to spec, inspect belt tension, verify
    # E-stop) a technician actually checks off on the generated work
    # order - copied onto WorkOrder.checklist_template at generation time
    # (maintenance.services.generate_due_work_orders), same as
    # assigned_team. Optional: description above still covers ad-hoc PM
    # that doesn't warrant a formal checklist.
    checklist_template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="pm_schedules"
    )

    # Copied onto WorkOrder.assigned_team by the generation service each
    # time a work order is created from this schedule - the "shift-aware
    # scheduling" the feature draft asked for, without needing the PM
    # engine itself to know anything about shift timing.
    assigned_team = models.ForeignKey(
        "teams.Team", on_delete=models.SET_NULL, null=True, blank=True, related_name="pm_schedules"
    )

    interval_days = models.PositiveIntegerField(help_text="Repeat every N days")
    start_date = models.DateField(help_text="Anchor date the recurrence is calculated from")

    # Denormalized rather than computed on the fly so "which schedules are
    # due" is a plain indexed query (`next_due_date__lte=today`) instead of
    # recomputing recurrence in Python for every row on every check.
    next_due_date = models.DateField()
    last_generated_work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    priority = models.CharField(max_length=10, choices=WorkOrder.Priority.choices, default=WorkOrder.Priority.MEDIUM)
    is_active = models.BooleanField(default=True, help_text="Pause without deleting")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.asset.tag} (every {self.interval_days}d)"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.next_due_date:
            self.next_due_date = self.start_date
        super().save(*args, **kwargs)


class PMScheduleGeneration(ImmutableModel):
    """Append-only record of every time a PMSchedule actually produced a
    WorkOrder - the audit trail behind future PM-compliance reporting
    (on-time %, overdue backlog)."""

    pm_schedule = models.ForeignKey(PMSchedule, on_delete=models.PROTECT, related_name="generations")
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="pm_generation")
    due_date_at_generation = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pm_schedule} -> {self.work_order} (due {self.due_date_at_generation})"
