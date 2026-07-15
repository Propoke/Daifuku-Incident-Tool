from django.utils import timezone

from assets.access import scope_queryset_to_sites
from workorders.models import WorkOrder

from .models import Team


def dispatch_board(user, date=None):
    """Work orders with a scheduled visit on `date` (defaults to today),
    grouped by assigned_team (or "Unassigned"), site-scoped like
    everything else. View-only for this pass - rescheduling still happens
    through the WorkOrder admin, not a drag-drop board here."""
    date = date or timezone.localdate()

    queryset = scope_queryset_to_sites(user, WorkOrder.objects.all(), "asset__terminal__site_id")
    queryset = queryset.filter(scheduled_start__date=date).select_related(
        "asset", "assigned_team", "assigned_to"
    ).order_by("scheduled_start")

    teams_qs = scope_queryset_to_sites(user, Team.objects.all(), "site_id")

    by_team = {team: [] for team in teams_qs}
    unassigned = []
    for work_order in queryset:
        if work_order.assigned_team_id and work_order.assigned_team in by_team:
            by_team[work_order.assigned_team].append(work_order)
        elif work_order.assigned_team_id:
            # Team assigned but outside the user's site scope (shouldn't
            # normally happen since the WO itself is already site-scoped,
            # but the team object might differ) - fold into unassigned
            # rather than silently dropping it.
            unassigned.append(work_order)
        else:
            unassigned.append(work_order)

    return {"date": date, "by_team": by_team, "unassigned": unassigned}
