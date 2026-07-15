"""Site-scoped data access.

Implements the "enforce at the query layer, not just the UI" recommendation
from the architecture audit in docs/cmms-feature-draft.md: a user only sees
tickets/stock/assets for their assigned site(s), enforced by filtering the
actual queryset (so it also blocks direct-URL/API access to an
out-of-scope object, not just hiding it from a list).

Orthogonal to the RBAC roles in core/migrations/000*_*.py: role permissions
control WHAT a user can do (add/change/view a given model); site access
controls WHICH rows of that model they can do it to.

Every Asset requires a Terminal (Site -> Terminal -> Asset), regardless of
who owns it - ownership (Asset.owner_customer) is a separate, purely
identifying attribute (for billing/warranty/contract purposes), not an
access-control one. A customer-owned asset physically sitting at one of
our Sites is scoped exactly like an internally-owned one: by that Site,
not by who owns it. There is deliberately no separate customer-based
scoping axis - site access is the only gate.
"""

BYPASS_GROUPS = ["Admin", "OEM"]


def get_accessible_site_ids(user):
    """None means unrestricted (superuser, or member of Admin/OEM).
    Otherwise a set of Site ids - a user with no assignment at all gets an
    empty set (sees no site-scoped data), not unrestricted access - fail
    closed."""
    if user.is_superuser:
        return None
    if user.groups.filter(name__in=BYPASS_GROUPS).exists():
        return None

    site_ids = set(user.accessible_sites.values_list("id", flat=True))
    for group in user.groups.all():
        site_ids.update(group.accessible_sites.values_list("id", flat=True))
    return site_ids


def scope_queryset_to_sites(user, queryset, site_lookup):
    """Filter `queryset` to `user`'s accessible sites via `site_lookup`, a
    Django ORM lookup path to Site's pk (e.g. "terminal__site_id" for
    Asset, "site_id" for Terminal/StockLocation themselves)."""
    site_ids = get_accessible_site_ids(user)
    if site_ids is None:
        return queryset
    return queryset.filter(**{f"{site_lookup}__in": site_ids})


class SiteScopedAdminMixin:
    """Applies scope_queryset_to_sites() to a ModelAdmin's queryset. Set
    `site_lookup` on the subclass. Overriding get_queryset() covers both
    the list view and get_object() (Django admin's object-level lookups go
    through the same queryset), so a direct URL to an out-of-scope
    object's change page 404s rather than just being hidden from the
    list."""

    site_lookup = None

    def get_queryset(self, request):
        assert self.site_lookup, f"{type(self).__name__} must set site_lookup"
        queryset = super().get_queryset(request)
        return scope_queryset_to_sites(request.user, queryset, self.site_lookup)
