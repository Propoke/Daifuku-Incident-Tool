from django.db.models import Count, DecimalField, DurationField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from assets.access import get_accessible_site_ids
from maintenance.models import PMScheduleGeneration
from workorders.models import WorkOrder, WorkOrderLaborEntry, WorkOrderPartUsage
from workorders.sla import get_sla_status

DEFAULT_PERIOD_DAYS = 90


def _site_scope(user, queryset, lookup):
    site_ids = get_accessible_site_ids(user)
    if site_ids is None:
        return queryset
    return queryset.filter(**{f"{lookup}__in": site_ids})


def _since(period_days):
    return timezone.now() - timezone.timedelta(days=period_days)


def backlog_summary(user):
    """Open (non-closed) work orders, by status - a plain count, not
    time-windowed, since backlog is a snapshot of "right now"."""
    queryset = _site_scope(user, WorkOrder.objects.all(), "asset__terminal__site_id")
    queryset = queryset.exclude(status=WorkOrder.Status.CLOSED)
    return list(queryset.values("status").annotate(count=Count("id")).order_by("status"))


def mttr_hours(user, period_days=DEFAULT_PERIOD_DAYS):
    """Mean Time To Repair: average actual_open_time -> actual_close_time
    for corrective work orders closed in the period."""
    queryset = _site_scope(user, WorkOrder.objects.all(), "asset__terminal__site_id")
    queryset = queryset.filter(
        work_order_type=WorkOrder.Type.CORRECTIVE,
        actual_close_time__isnull=False,
        actual_open_time__isnull=False,
        actual_close_time__gte=_since(period_days),
    )
    duration = ExpressionWrapper(F("actual_close_time") - F("actual_open_time"), output_field=DurationField())
    result = queryset.annotate(repair_time=duration).aggregate(count=Count("id"), total=Sum("repair_time"))
    if not result["count"]:
        return None
    avg_seconds = result["total"].total_seconds() / result["count"]
    return round(avg_seconds / 3600, 1)


def pm_compliance(user, period_days=DEFAULT_PERIOD_DAYS):
    """Share of PM-generated work orders closed on or before their due
    date, among those generated in the period."""
    queryset = _site_scope(
        user, PMScheduleGeneration.objects.all(), "work_order__asset__terminal__site_id"
    )
    queryset = queryset.filter(generated_at__gte=_since(period_days)).select_related("work_order")

    total = 0
    on_time = 0
    for generation in queryset:
        total += 1
        wo = generation.work_order
        if wo.status == WorkOrder.Status.CLOSED and wo.actual_close_time is not None:
            if wo.actual_close_time.date() <= generation.due_date_at_generation:
                on_time += 1

    if total == 0:
        return None
    return round(100 * on_time / total, 1)


def parts_cost_total(user, period_days=DEFAULT_PERIOD_DAYS):
    queryset = _site_scope(user, WorkOrderPartUsage.objects.all(), "work_order__asset__terminal__site_id")
    queryset = queryset.filter(date__gte=_since(period_days).date())
    line_cost = ExpressionWrapper(
        F("quantity") * Coalesce(F("spare_part__unit_cost"), 0), output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    result = queryset.annotate(line_cost=line_cost).aggregate(total=Sum("line_cost"))
    return result["total"] or 0


def labor_hours_total(user, period_days=DEFAULT_PERIOD_DAYS):
    queryset = _site_scope(user, WorkOrderLaborEntry.objects.all(), "work_order__asset__terminal__site_id")
    queryset = queryset.filter(date__gte=_since(period_days).date())
    return queryset.aggregate(total=Sum("hours"))["total"] or 0


def top_downtime_assets(user, period_days=DEFAULT_PERIOD_DAYS, limit=5):
    """Assets with the most corrective downtime (actual_open_time ->
    actual_close_time) in the period."""
    queryset = _site_scope(user, WorkOrder.objects.all(), "asset__terminal__site_id")
    queryset = queryset.filter(
        work_order_type=WorkOrder.Type.CORRECTIVE,
        actual_close_time__isnull=False,
        actual_open_time__isnull=False,
        actual_close_time__gte=_since(period_days),
    )
    duration = ExpressionWrapper(F("actual_close_time") - F("actual_open_time"), output_field=DurationField())
    rows = (
        queryset.annotate(repair_time=duration)
        .values("asset__tag", "asset__name")
        .annotate(total_downtime=Sum("repair_time"), incident_count=Count("id"))
        .order_by("-total_downtime")[:limit]
    )
    return [
        {
            "asset_tag": row["asset__tag"],
            "asset_name": row["asset__name"],
            "downtime_hours": round(row["total_downtime"].total_seconds() / 3600, 1),
            "incident_count": row["incident_count"],
        }
        for row in rows
    ]


def sla_summary(user):
    """SLA status across open work orders for customer-owned assets under
    contract. Customer-owned assets have no Site (Asset.terminal is null),
    so the same site-scoping filter used everywhere else naturally makes
    this report visible only to Admin/OEM for now - consistent with the
    customer-data-segregation boundary noted in assets/access.py, not a
    separate rule invented here.
    """
    queryset = _site_scope(user, WorkOrder.objects.all(), "asset__terminal__site_id")
    queryset = queryset.exclude(status=WorkOrder.Status.CLOSED).filter(asset__service_contract__isnull=False)
    queryset = queryset.select_related("asset__service_contract").prefetch_related("status_changes")

    counts = {"met": 0, "pending": 0, "breached": 0, "overdue": 0, "no_sla": 0}
    for work_order in queryset:
        status = get_sla_status(work_order)
        if status is None:
            counts["no_sla"] += 1
            continue
        # Worst-of response/resolution status represents this ticket.
        statuses = [v["status"] for k, v in status.items() if k in ("response", "resolution")]
        if "breached" in statuses:
            counts["breached"] += 1
        elif "overdue" in statuses:
            counts["overdue"] += 1
        elif "pending" in statuses:
            counts["pending"] += 1
        else:
            counts["met"] += 1
    return counts


def dashboard_data(user, period_days=DEFAULT_PERIOD_DAYS):
    return {
        "period_days": period_days,
        "backlog": backlog_summary(user),
        "mttr_hours": mttr_hours(user, period_days),
        "pm_compliance_pct": pm_compliance(user, period_days),
        "parts_cost_total": parts_cost_total(user, period_days),
        "labor_hours_total": labor_hours_total(user, period_days),
        "sla_summary": sla_summary(user),
        "top_downtime_assets": top_downtime_assets(user, period_days),
    }
