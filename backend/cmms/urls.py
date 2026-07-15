from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_static

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

# django.conf.urls.static.static() only ever adds a pattern when DEBUG is
# True (a hardcoded safety guard inside Django itself, not something a
# wrapping `if settings.DEBUG:` here controls), so it can't be used to
# serve media outside dev. Nothing served MEDIA_URL in a real deployment
# before this - attachments would have uploaded fine but 404'd on
# download. Using django.views.static.serve directly instead: Django's
# own docs call this view unsuitable for production/high-traffic use, but
# for an internal-network-only, Standard-tier single-VM deployment (the
# infra plan's stated scope), it's an honest, working stopgap - the real
# fix is object storage (MinIO, already flagged in the infra plan and
# still not wired up).
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve_static, {"document_root": settings.MEDIA_ROOT}),
]
