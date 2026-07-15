from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render


def healthz(request):
    return JsonResponse({"status": "ok"})


@login_required
def home(request):
    return render(request, "core/home.html", {"user": request.user})
