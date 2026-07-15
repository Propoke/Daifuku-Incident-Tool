from django.conf import settings
from django.db import models

from assets.models import SparePart, Site
from workorders.models import WorkOrder


class StockLocation(models.Model):
    """A storeroom/warehouse/bin within a Site - the "location" a technician
    needs to actually find a part."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="stock_locations")
    name = models.CharField(max_length=200, help_text='e.g. "Main Warehouse", "Bin A-12"')
    code = models.CharField(max_length=50)

    class Meta:
        unique_together = ("site", "code")

    def __str__(self):
        return f"{self.site.code}/{self.code} ({self.name})"


class StockLevel(models.Model):
    """Quantity of a SparePart on hand at a specific StockLocation."""

    spare_part = models.ForeignKey(SparePart, on_delete=models.PROTECT, related_name="stock_levels")
    stock_location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="stock_levels")
    quantity_on_hand = models.PositiveIntegerField(default=0)
    min_quantity = models.PositiveIntegerField(default=0, help_text="Reorder threshold")
    max_quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("spare_part", "stock_location")

    def __str__(self):
        return f"{self.spare_part.sku} @ {self.stock_location}: {self.quantity_on_hand}"

    @property
    def quantity_reserved(self):
        return (
            self.reservations.filter(status=StockReservation.Status.RESERVED).aggregate(
                total=models.Sum("quantity")
            )["total"]
            or 0
        )

    @property
    def quantity_available(self):
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def needs_reorder(self):
        return self.quantity_on_hand <= self.min_quantity


class StockReservation(models.Model):
    """A planned allocation of stock to a work order, ahead of actually
    taking the part off the shelf. Doesn't touch quantity_on_hand -
    StockLevel.quantity_available accounts for active reservations so
    other jobs don't plan against stock that's already spoken for.

    Not enforced yet: a walk-up barcode consumption (inventory.services.
    consume_stock) only checks physical quantity_on_hand, not whether doing
    so eats into another work order's reservation. Flagged as a known gap
    rather than built now - see docs/mobile-app-backlog.md.
    """

    class Status(models.TextChoices):
        RESERVED = "RESERVED", "Reserved"
        FULFILLED = "FULFILLED", "Fulfilled"
        CANCELLED = "CANCELLED", "Cancelled"

    stock_level = models.ForeignKey(StockLevel, on_delete=models.PROTECT, related_name="reservations")
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="stock_reservations")
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RESERVED)
    reserved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reserved_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.quantity}x {self.stock_level.spare_part.sku} for {self.work_order} ({self.status})"
