from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from .services import DEFAULT_PERIOD_DAYS, asset_history, dashboard_data, get_accessible_asset_or_none


@login_required
def dashboard(request):
    period_days = int(request.GET.get("days", DEFAULT_PERIOD_DAYS))
    data = dashboard_data(request.user, period_days=period_days)
    return render(request, "reporting/dashboard.html", data)


@login_required
def asset_history_view(request, asset_id):
    asset = get_accessible_asset_or_none(request.user, asset_id)
    if asset is None:
        raise Http404("No asset matches this id, or it isn't at one of your sites.")
    return render(request, "reporting/asset_history.html", asset_history(asset))
