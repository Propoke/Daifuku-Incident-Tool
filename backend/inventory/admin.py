from django.contrib import admin

from assets.access import SiteScopedAdminMixin

from .models import StockLevel, StockLocation, StockReservation


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
