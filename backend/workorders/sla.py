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
