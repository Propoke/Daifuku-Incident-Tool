from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import DEFAULT_PERIOD_DAYS, dashboard_data


@login_required
def dashboard(request):
    period_days = int(request.GET.get("days", DEFAULT_PERIOD_DAYS))
    data = dashboard_data(request.user, period_days=period_days)
    return render(request, "reporting/dashboard.html", data)
