from django.db import models

from assets.models import Asset, AssetMeterReading, ImmutableModel
from core.models import ChecklistTemplate
from workorders.models import WorkOrder


class PMSchedule(models.Model):
    """A recurring preventive-maintenance trigger for one asset.

    Two triggers can be active at once - a calendar interval
    (interval_days, always required) and an optional meter-based one
    (meter_type/meter_interval) - whichever fires first generates the
    work order (maintenance.services.generate_due_work_orders). Material
    handling equipment duty cycle varies far more than the calendar does,
    so usage-based PM (every N running hours/cycles) is often the primary
    trigger in practice, not calendar-based - this was flagged as a known
    gap when PM scheduling was first built (it depended on equipment
    actually reporting meter readings, which assets.AssetMeterReading now
    provides via manual entry).
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

    # Optional meter-based trigger, alongside the calendar one above.
    # next_due_meter_value is denormalized the same way next_due_date is -
    # a plain comparison against the asset's latest reading, not
    # recomputed from full reading history on every check.
    meter_type = models.CharField(max_length=20, choices=AssetMeterReading.MeterType.choices, blank=True)
    meter_interval = models.PositiveIntegerField(
        null=True, blank=True, help_text="Repeat every N meter units (hours or cycles) - requires meter_type"
    )
    next_due_meter_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

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
        if self._state.adding and self.meter_type and self.meter_interval and self.next_due_meter_value is None:
            anchor = AssetMeterReading.latest_value(self.asset, self.meter_type) or 0
            self.next_due_meter_value = anchor + self.meter_interval
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
