"""Tests for the purchase-order receiving workflow: cumulative
quantity_received drives stock, rolls PO status up, and refuses illegal
transitions.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from assets.models import Site, SparePart, Vendor
from inventory.models import PurchaseOrder, PurchaseOrderLine, StockLevel, StockLocation


class PurchaseOrderReceivingTests(TestCase):
    def setUp(self):
        self.vendor = Vendor.objects.create(name="v")
        self.site = Site.objects.create(name="S", code="S")
        self.loc = StockLocation.objects.create(site=self.site, code="LOC", name="loc")
        self.part = SparePart.objects.create(sku="SKU", description="p")
        self.po = PurchaseOrder.objects.create(vendor=self.vendor, stock_location=self.loc, status="ORDERED")
        self.line = PurchaseOrderLine.objects.create(
            purchase_order=self.po, spare_part=self.part, quantity_ordered=10
        )

    def test_stock_level_absent_until_first_receipt(self):
        self.assertFalse(StockLevel.objects.filter(spare_part=self.part, stock_location=self.loc).exists())

    def test_partial_receive_adds_stock_and_sets_partial_status(self):
        self.line.quantity_received = 4
        self.line.save()
        sl = StockLevel.objects.get(spare_part=self.part, stock_location=self.loc)
        self.assertEqual(sl.quantity_on_hand, 4)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.Status.PARTIALLY_RECEIVED)

    def test_full_receive_sets_received_status(self):
        self.line.quantity_received = 10
        self.line.save()
        sl = StockLevel.objects.get(spare_part=self.part, stock_location=self.loc)
        self.assertEqual(sl.quantity_on_hand, 10)
        self.po.refresh_from_db()
        self.assertEqual(self.po.status, PurchaseOrder.Status.RECEIVED)

    def test_incremental_receipts_accumulate(self):
        self.line.quantity_received = 4
        self.line.save()
        self.line.quantity_received = 10
        self.line.save()
        sl = StockLevel.objects.get(spare_part=self.part, stock_location=self.loc)
        self.assertEqual(sl.quantity_on_hand, 10)

    def test_cannot_decrease_received(self):
        self.line.quantity_received = 5
        self.line.save()
        self.line.quantity_received = 3
        with self.assertRaises(ValidationError):
            self.line.save()

    def test_cannot_over_receive(self):
        self.line.quantity_received = 11
        with self.assertRaises(ValidationError):
            self.line.save()
