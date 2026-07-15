from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def get_customer_contact(user):
    return getattr(user, "customer_contact", None)


def portal_login_required(view_func):
    """Deliberately not django.contrib.auth.login_required: the site-wide
    LOGIN_URL points at the Entra OIDC flow, which is wrong for customer
    portal accounts. Checks for a CustomerContact profile, not is_staff -
    internal staff authenticated via Entra have no CustomerContact and are
    correctly denied here, the same way portal accounts (never is_staff)
    are denied by Django admin."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("portal-login")
        if get_customer_contact(request.user) is None:
            raise PermissionDenied("This account is not a customer portal account.")
        return view_func(request, *args, **kwargs)

    return wrapped
