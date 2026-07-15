from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("api/mobile/", include("mobile_api.urls")),
    path("reports/", include("reporting.urls")),
    path("dispatch/", include("teams.urls")),
    path("portal/", include("portal.urls")),
    path("app/", include("pwa.urls")),
    path("", include("core.urls")),
]
