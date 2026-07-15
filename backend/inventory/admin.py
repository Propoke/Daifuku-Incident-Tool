from django.contrib import admin

from assets.access import SiteScopedAdminMixin

from .models import PurchaseOrder, PurchaseOrderLine, StockLevel, StockLocation, StockReservation


@admin.register(StockLocation)
class StockLocationAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "site_id"
    list_display = ("code", "name", "site")
    list_filter = ("site",)
    search_fields = ("code", "name")


@admin.register(StockLevel)
class StockLevelAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "stock_location__site_id"
    list_display = (
        "spare_part",
        "stock_location",
        "quantity_on_hand",
        "quantity_reserved",
        "quantity_available",
        "needs_reorder",
    )
    list_filter = ("stock_location__site", "stock_location")
    search_fields = ("spare_part__sku", "spare_part__barcode")

    @admin.display(boolean=True)
    def needs_reorder(self, obj):
        return obj.needs_reorder


@admin.register(StockReservation)
class StockReservationAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "stock_level__stock_location__site_id"
    list_display = ("stock_level", "work_order", "quantity", "status", "reserved_by", "reserved_at")
    list_filter = ("status",)


class PurchaseOrderLineInline(admin.TabularInline):
    """quantity_received is cumulative, not a delta - raising it here *is*
    the receiving action (see PurchaseOrderLine.save()): the increase gets
    added to the matching StockLevel and the parent PO's status advances
    automatically. This is a plain editable inline, not add-only - unlike
    Attachment/Comment/ChecklistResponse elsewhere in this repo, editing
    an existing row is the intended workflow here, and Django's default
    formset.save() already calls each instance's own save() (which is
    where the actual logic lives), so no save_formset override is needed."""

    model = PurchaseOrderLine
    extra = 1
    fields = ("spare_part", "quantity_ordered", "quantity_received", "unit_cost")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(SiteScopedAdminMixin, admin.ModelAdmin):
    site_lookup = "stock_location__site_id"
    list_display = ("__str__", "vendor", "stock_location", "status", "ordered_at", "expected_date")
    list_filter = ("status", "vendor")
    search_fields = ("vendor__name",)
    readonly_fields = ("created_by", "created_at")
    inlines = [PurchaseOrderLineInline]

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
