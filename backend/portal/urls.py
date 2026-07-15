from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.portal_login, name="portal-login"),
    path("logout/", views.portal_logout, name="portal-logout"),
    path("tickets/", views.portal_tickets, name="portal-tickets"),
    path("tickets/<int:pk>/", views.portal_ticket_detail, name="portal-ticket-detail"),
    path("report-issue/", views.portal_report_issue, name="portal-report-issue"),
    path("", views.portal_home, name="portal-home"),
]
