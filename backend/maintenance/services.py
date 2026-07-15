import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from assets.models import AssetMeterReading
from workorders.models import WorkOrder

from .models import PMSchedule, PMScheduleGeneration


def generate_due_work_orders(as_of=None):
    """Create one WorkOrder for every PMSchedule that's due - calendar or
    meter-based, whichever fires first - advance the schedule's trigger(s)
    past `as_of`/the current meter reading, and record the generation.

    Called from both the `generate_due_pm_work_orders` management command
    and the Celery beat task - kept here as a plain function so neither
    depends on the other and both stay trivial wrappers.

    If a schedule is overdue by more than one interval (e.g. the check
    didn't run for a while), this generates a single catch-up WorkOrder
    rather than one per missed period, then advances the trigger(s) past
    `as_of`/the current reading so it doesn't re-fire on the next check.
    """
    as_of = as_of or timezone.localdate()
    created = []

    # The meter-trigger check itself needs the asset's latest reading,
    # which isn't expressible as a plain indexed comparison the way
    # next_due_date__lte=as_of is - so this can't narrow to "meter-due"
    # rows at the DB level the way it can for calendar-due ones. It still
    # narrows to "calendar-due, or has a meter trigger configured at all",
    # rather than scanning every active schedule regardless of relevance.
    candidate_schedules = PMSchedule.objects.select_for_update().filter(is_active=True).filter(
        Q(next_due_date__lte=as_of) | (Q(meter_type__gt="") & Q(meter_interval__isnull=False))
    )
    with transaction.atomic():
        for schedule in candidate_schedules:
            calendar_due = schedule.next_due_date <= as_of

            meter_due = False
            current_meter_value = None
            if schedule.meter_type and schedule.meter_interval and schedule.next_due_meter_value is not None:
                current_meter_value = AssetMeterReading.latest_value(schedule.asset, schedule.meter_type)
                if current_meter_value is not None:
                    meter_due = current_meter_value >= schedule.next_due_meter_value

            if not (calendar_due or meter_due):
                continue

            work_order = WorkOrder.objects.create(
                asset=schedule.asset,
                work_order_type=WorkOrder.Type.PREVENTIVE,
                priority=schedule.priority,
                title=schedule.title,
                description=schedule.description,
                due_date=schedule.next_due_date,
                assigned_team=schedule.assigned_team,
                checklist_template=schedule.checklist_template,
            )
            PMScheduleGeneration.objects.create(
                pm_schedule=schedule,
                work_order=work_order,
                due_date_at_generation=schedule.next_due_date,
            )

            schedule.last_generated_work_order = work_order
            while schedule.next_due_date <= as_of:
                schedule.next_due_date += datetime.timedelta(days=schedule.interval_days)
            if meter_due:
                while schedule.next_due_meter_value <= current_meter_value:
                    schedule.next_due_meter_value += schedule.meter_interval
            schedule.save()

            created.append(work_order)

    return created
