from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="reporting-dashboard"),
    path("assets/<int:asset_id>/history/", views.asset_history_view, name="asset-history"),
]
