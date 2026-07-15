from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from workorders.models import WorkOrder

from .forms import IssueReportForm
from .search import global_search


def healthz(request):
    return JsonResponse({"status": "ok"})


@login_required
def home(request):
    return render(request, "core/home.html", {"user": request.user})


@login_required
def report_issue(request):
    if request.method == "POST":
        form = IssueReportForm(request.POST, user=request.user)
        if form.is_valid():
            work_order = form.save(commit=False)
            work_order.work_order_type = WorkOrder.Type.CORRECTIVE
            work_order.reported_by = request.user
            work_order.save()
            return redirect("my-tickets")
    else:
        form = IssueReportForm(user=request.user)
    return render(request, "core/report_issue.html", {"form": form})


@login_required
def my_tickets(request):
    tickets = WorkOrder.objects.filter(reported_by=request.user).order_by("-created_at")
    return render(request, "core/my_tickets.html", {"tickets": tickets})


@login_required
def search(request):
    query = request.GET.get("q", "")
    results = global_search(request.user, query)
    return render(request, "core/search.html", {"query": query, "results": results})
