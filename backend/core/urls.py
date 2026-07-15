from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("report-issue/", views.report_issue, name="report-issue"),
    path("my-tickets/", views.my_tickets, name="my-tickets"),
    path("", views.home, name="home"),
]
