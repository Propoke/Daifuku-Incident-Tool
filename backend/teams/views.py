import datetime

from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

from .services import dispatch_board


@login_required
@permission_required("workorders.view_workorder", raise_exception=True)
def dispatch_board_view(request):
    date_str = request.GET.get("date")
    date = datetime.date.fromisoformat(date_str) if date_str else None
    data = dispatch_board(request.user, date=date)
    return render(request, "teams/dispatch_board.html", data)
