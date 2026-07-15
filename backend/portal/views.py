from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import get_object_or_404, redirect, render

from workorders.models import WorkOrder

from .auth import get_customer_contact, portal_login_required
from .forms import PortalIssueReportForm


def portal_login(request):
    if request.user.is_authenticated and get_customer_contact(request.user):
        return redirect("portal-home")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if get_customer_contact(user) is None:
                form.add_error(None, "This account is not a customer portal account.")
            else:
                auth_login(request, user)
                return redirect("portal-home")
    else:
        form = AuthenticationForm()
    return render(request, "portal/login.html", {"form": form})


def portal_logout(request):
    auth_logout(request)
    return redirect("portal-login")


@portal_login_required
def portal_home(request):
    contact = get_customer_contact(request.user)
    tickets = WorkOrder.objects.filter(asset__owner_customer=contact.customer).order_by("-created_at")[:10]
    return render(request, "portal/home.html", {"contact": contact, "tickets": tickets})


@portal_login_required
def portal_tickets(request):
    contact = get_customer_contact(request.user)
    tickets = WorkOrder.objects.filter(asset__owner_customer=contact.customer).order_by("-created_at")
    return render(request, "portal/tickets.html", {"contact": contact, "tickets": tickets})


@portal_login_required
def portal_ticket_detail(request, pk):
    contact = get_customer_contact(request.user)
    ticket = get_object_or_404(WorkOrder, pk=pk, asset__owner_customer=contact.customer)
    return render(request, "portal/ticket_detail.html", {"contact": contact, "ticket": ticket})


@portal_login_required
def portal_report_issue(request):
    contact = get_customer_contact(request.user)
    if request.method == "POST":
        form = PortalIssueReportForm(request.POST, customer=contact.customer)
        if form.is_valid():
            work_order = form.save(commit=False)
            work_order.work_order_type = WorkOrder.Type.CORRECTIVE
            work_order.reported_by = request.user
            work_order.save()
            return redirect("portal-ticket-detail", pk=work_order.pk)
    else:
        form = PortalIssueReportForm(customer=contact.customer)
    return render(request, "portal/report_issue.html", {"contact": contact, "form": form})
