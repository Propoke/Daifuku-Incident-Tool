from django.db.models import Q

from assets.access import scope_queryset_to_sites
from assets.models import Asset, SparePart
from workorders.models import WorkOrder

RESULTS_PER_TYPE = 25


def global_search(user, query):
    """Search assets/tickets/parts by tag/barcode/title/description -
    flagged as a requirement back in the original architecture audit,
    never built until now. Django admin's per-model search only helps
    once you already know which model you're looking in.

    Assets and work orders are site-scoped the same way every other view
    in this repo is. The spare part catalog itself is global, matching
    mobile_api.SparePartLookupView's existing treatment - only stock
    levels are site-scoped, not the catalog.
    """
    query = (query or "").strip()
    if not query:
        return {"assets": [], "work_orders": [], "spare_parts": []}

    assets = scope_queryset_to_sites(user, Asset.objects.all(), "terminal__site_id").filter(
        Q(tag__icontains=query) | Q(name__icontains=query) | Q(serial_number__icontains=query)
    )[:RESULTS_PER_TYPE]

    work_orders = (
        scope_queryset_to_sites(user, WorkOrder.objects.all(), "asset__terminal__site_id")
        .filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(asset__tag__icontains=query))
        .select_related("asset")[:RESULTS_PER_TYPE]
    )

    spare_parts = SparePart.objects.filter(
        Q(sku__icontains=query) | Q(barcode__icontains=query) | Q(description__icontains=query)
    )[:RESULTS_PER_TYPE]

    return {"assets": assets, "work_orders": work_orders, "spare_parts": spare_parts}
