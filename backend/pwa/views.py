from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@login_required
def app_shell(request):
    return render(request, "pwa/shell.html")


@never_cache
def service_worker(request):
    # Served at /app/sw.js (not /static/pwa/sw.js) so its default scope is
    # /app/* - a service worker's scope is the directory of its own URL
    # unless the server sends a Service-Worker-Allowed header, and this is
    # simpler than fiddling with that header.
    return render(request, "pwa/sw.js", content_type="application/javascript")
