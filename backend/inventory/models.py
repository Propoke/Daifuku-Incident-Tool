from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from assets.models import SparePart, Site, Vendor
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


class PurchaseOrder(models.Model):
    """The answer StockLevel.needs_reorder never had a next step for: "this
    part is on order, ETA Tuesday." status is derived from its lines'
    receiving progress (see PurchaseOrderLine.save()/refresh_status
    below), not hand-set - DRAFT/ORDERED are the only states set directly
    by a user; PARTIALLY_RECEIVED/RECEIVED happen automatically as lines
    get received."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ORDERED = "ORDERED", "Ordered"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially received"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="purchase_orders")
    stock_location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        help_text="Where received stock will be added",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    ordered_at = models.DateField(null=True, blank=True)
    expected_date = models.DateField(null=True, blank=True, help_text="ETA")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PO-{self.pk} - {self.vendor} ({self.get_status_display()})"

    def refresh_status(self):
        """Rolls status up to PARTIALLY_RECEIVED/RECEIVED based on line
        receiving progress - called by PurchaseOrderLine.save() whenever a
        line's quantity_received changes. Never overrides DRAFT/CANCELLED
        (those are set directly by a user, not derived)."""
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED):
            return
        lines = list(self.lines.all())
        if not lines:
            return
        if all(line.quantity_received >= line.quantity_ordered for line in lines):
            new_status = self.Status.RECEIVED
        elif any(line.quantity_received > 0 for line in lines):
            new_status = self.Status.PARTIALLY_RECEIVED
        else:
            new_status = self.Status.ORDERED
        if new_status != self.status:
            self.status = new_status
            self.save(update_fields=["status"])


class PurchaseOrderLine(models.Model):
    """One SparePart/quantity on a PurchaseOrder. quantity_received is
    cumulative (odometer-style, like assets.AssetMeterReading.value) -
    editing it upward is the actual receiving action: the delta gets
    added to the matching StockLevel at the PO's stock_location, and the
    parent PurchaseOrder's status rolls up automatically. It can never be
    decreased once recorded, since that would mean un-receiving stock
    that's already been added to StockLevel."""

    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    spare_part = models.ForeignKey(SparePart, on_delete=models.PROTECT, related_name="purchase_order_lines")
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.spare_part.sku} x{self.quantity_ordered} ({self.purchase_order})"

    @property
    def is_fully_received(self):
        return self.quantity_received >= self.quantity_ordered

    def save(self, *args, **kwargs):
        previous_received = 0
        if not self._state.adding:
            previous_received = (
                PurchaseOrderLine.objects.filter(pk=self.pk).values_list("quantity_received", flat=True).first() or 0
            )

        if self.quantity_received > self.quantity_ordered:
            raise ValidationError("quantity_received cannot exceed quantity_ordered.")
        delta = self.quantity_received - previous_received
        if delta < 0:
            raise ValidationError(
                "quantity_received cannot be decreased - it represents stock already added to inventory."
            )

        super().save(*args, **kwargs)

        if delta > 0:
            stock_level, _ = StockLevel.objects.get_or_create(
                spare_part=self.spare_part, stock_location=self.purchase_order.stock_location
            )
            stock_level.quantity_on_hand += delta
            stock_level.save()

        self.purchase_order.refresh_status()
