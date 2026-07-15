from django.urls import path

from . import views

urlpatterns = [
    path("sw.js", views.service_worker, name="pwa-service-worker"),
    path("", views.app_shell, name="pwa-app"),
]
