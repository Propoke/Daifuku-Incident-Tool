from django.conf import settings
from django.db import models

from assets.models import Asset, Site
from core.models import ChecklistTemplate
from workorders.models import WorkOrder

# Calibration/inspection due-date tracking (feature draft §11) isn't a
# separate model here - it's the same recurring-due-date-generates-a-
# work-order shape as maintenance.PMSchedule, so a calibration due date is
# just a PMSchedule with a descriptive title rather than a duplicated
# mechanism.


class PermitToWork(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="permits_to_work")
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="permits_to_work"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # Reference-only for now: the step-by-step LOTO procedure to follow,
    # shown alongside the permit. Response capture (who actually checked
    # off which step) is only built for WorkOrder so far
    # (workorders.models.WorkOrderChecklistResponse) - a permit-level
    # equivalent is a known follow-up, not built in this pass.
    checklist_template = models.ForeignKey(
        ChecklistTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="permits_to_work"
    )
    lockout_tagout_applied = models.BooleanField(default=False)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="permits_issued"
    )
    issued_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="permits_received"
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"PTW: {self.title} - {self.asset.tag}"


class IncidentReport(models.Model):
    class Severity(models.TextChoices):
        NEAR_MISS = "NEAR_MISS", "Near miss"
        MINOR = "MINOR", "Minor"
        MODERATE = "MODERATE", "Moderate"
        SEVERE = "SEVERE", "Severe"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_INVESTIGATION = "UNDER_INVESTIGATION", "Under investigation"
        CLOSED = "CLOSED", "Closed"

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="incident_reports")
    asset = models.ForeignKey(
        Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name="incident_reports"
    )
    related_work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name="related_incident_reports"
    )
    severity = models.CharField(max_length=20, choices=Severity.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    occurred_at = models.DateTimeField()
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="incident_reports"
    )
    description = models.TextField()
    immediate_action_taken = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_severity_display()} incident at {self.site.code} ({self.occurred_at:%Y-%m-%d})"
