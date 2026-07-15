from django.urls import path

from . import views

urlpatterns = [
    path("", views.dispatch_board_view, name="dispatch-board"),
]
