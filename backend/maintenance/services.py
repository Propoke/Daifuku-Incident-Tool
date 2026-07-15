import datetime

from django.db import transaction
from django.utils import timezone

from workorders.models import WorkOrder

from .models import PMSchedule, PMScheduleGeneration


def generate_due_work_orders(as_of=None):
    """Create one WorkOrder for every PMSchedule that's due, advance each
    schedule's next_due_date past `as_of`, and record the generation.

    Called from both the `generate_due_pm_work_orders` management command
    and the Celery beat task - kept here as a plain function so neither
    depends on the other and both stay trivial wrappers.

    If a schedule is overdue by more than one interval (e.g. the check
    didn't run for a while), this generates a single catch-up WorkOrder
    rather than one per missed period, then advances next_due_date past
    `as_of` so it doesn't re-fire on the next check.
    """
    as_of = as_of or timezone.localdate()
    created = []

    due_schedules = PMSchedule.objects.select_for_update().filter(is_active=True, next_due_date__lte=as_of)
    with transaction.atomic():
        for schedule in due_schedules:
            work_order = WorkOrder.objects.create(
                asset=schedule.asset,
                work_order_type=WorkOrder.Type.PREVENTIVE,
                priority=schedule.priority,
                title=schedule.title,
                description=schedule.description,
                due_date=schedule.next_due_date,
                assigned_team=schedule.assigned_team,
            )
            PMScheduleGeneration.objects.create(
                pm_schedule=schedule,
                work_order=work_order,
                due_date_at_generation=schedule.next_due_date,
            )

            schedule.last_generated_work_order = work_order
            while schedule.next_due_date <= as_of:
                schedule.next_due_date += datetime.timedelta(days=schedule.interval_days)
            schedule.save()

            created.append(work_order)

    return created
