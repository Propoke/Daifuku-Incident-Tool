from django.utils import timezone

from .models import WorkOrder


def get_sla_status(work_order, as_of=None):
    """SLA status against the ServiceContract covering work_order.asset, if
    any. Returns None if the asset has no contract or the contract sets no
    SLA targets - most internal-owned assets, since ServiceContract only
    applies to customer-owned equipment (Asset.service_contract).

    Detection/visibility only - deliberately doesn't send notifications or
    auto-escalate. The architecture audit flagged SLA/escalation as likely
    to grow into its own subsystem; this is the measurement piece, not
    that subsystem.
    """
    contract = work_order.asset.service_contract
    if contract is None:
        return None
    if contract.sla_response_hours is None and contract.sla_resolution_hours is None:
        return None

    as_of = as_of or timezone.now()
    result = {"contract": contract}

    if contract.sla_response_hours is not None:
        first_in_progress = (
            work_order.status_changes.filter(to_status=WorkOrder.Status.IN_PROGRESS).order_by("changed_at").first()
        )
        if first_in_progress:
            elapsed_hours = (first_in_progress.changed_at - work_order.created_at).total_seconds() / 3600
            breached = elapsed_hours > contract.sla_response_hours
            status = "breached" if breached else "met"
        else:
            elapsed_hours = (as_of - work_order.created_at).total_seconds() / 3600
            breached = elapsed_hours > contract.sla_response_hours
            status = "overdue" if breached else "pending"
        result["response"] = {
            "target_hours": contract.sla_response_hours,
            "elapsed_hours": round(elapsed_hours, 1),
            "breached": breached,
            "status": status,
        }

    if contract.sla_resolution_hours is not None:
        if work_order.status == WorkOrder.Status.CLOSED and work_order.actual_close_time:
            elapsed_hours = (work_order.actual_close_time - work_order.created_at).total_seconds() / 3600
            breached = elapsed_hours > contract.sla_resolution_hours
            status = "breached" if breached else "met"
        else:
            elapsed_hours = (as_of - work_order.created_at).total_seconds() / 3600
            breached = elapsed_hours > contract.sla_resolution_hours
            status = "overdue" if breached else "pending"
        result["resolution"] = {
            "target_hours": contract.sla_resolution_hours,
            "elapsed_hours": round(elapsed_hours, 1),
            "breached": breached,
            "status": status,
        }

    return result


def breached_open_work_orders(user=None):
    """Open (non-CLOSED) work orders whose SLA response or resolution
    target is past due - either "breached" (work started/closed after the
    target) or "overdue" (target has passed and work hasn't even started
    yet, per get_sla_status's own distinction). Both mean an SLA problem a
    manager should hear about, so the digest doesn't split them the way
    reporting.services.sla_summary()'s dashboard counts do.

    When `user` is given, results are site-scoped to that user's
    accessible sites (assets.access) - the daily digest sends per-recipient
    so a manager assigned to one site never sees another site's tickets,
    the same visibility gate every other surface enforces. Called with no
    user, it's unscoped (all breaches).

    Used by core.notifications for the daily SLA-breach digest email -
    kept here rather than in reporting/services.py since it returns
    individual tickets like get_sla_status does, not an aggregate count."""
    queryset = (
        WorkOrder.objects.exclude(status=WorkOrder.Status.CLOSED)
        .filter(asset__service_contract__isnull=False)
        .select_related("asset__service_contract")
        .prefetch_related("status_changes")
    )
    if user is not None:
        # Imported here, not at module top, to keep sla.py free of an
        # assets.access dependency for every other caller of this module.
        from assets.access import scope_queryset_to_sites

        queryset = scope_queryset_to_sites(user, queryset, "asset__terminal__site_id")
    results = []
    for work_order in queryset:
        status = get_sla_status(work_order)
        if status is None:
            continue
        statuses = {v["status"] for k, v in status.items() if k in ("response", "resolution")}
        if statuses & {"breached", "overdue"}:
            results.append(work_order)
    return results
