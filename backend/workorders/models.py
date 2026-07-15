from django.conf import settings
from django.db import models
from django.utils import timezone

from assets.models import Asset, AssetConfigurationAssignment, ImmutableModel, SparePart


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

    failure_code = models.ForeignKey(
        FailureCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_orders"
    )

    due_date = models.DateField(null=True, blank=True)
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
        if not is_new:
            previous_status = WorkOrder.objects.filter(pk=self.pk).values_list("status", flat=True).first()

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
