from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from assets.models import SparePart
from workorders.models import WorkOrderPartUsage

from .models import StockLevel, StockReservation


def find_spare_part_by_code(code):
    """Barcode-scan lookup: try the barcode first, fall back to sku - a
    scanner may be pointed at either depending on what's printed on the
    part's label."""
    return SparePart.objects.filter(barcode=code).first() or SparePart.objects.filter(sku=code).first()


def consume_stock(*, work_order, spare_part, stock_location, quantity, user=None):
    """The barcode-scan "book a part out of stock onto a ticket" action:
    decrements on-hand quantity and records the usage against the work
    order, atomically.

    Checks physical quantity_on_hand only - doesn't yet prevent one work
    order's walk-up consumption from eating another work order's active
    StockReservation. See the note on StockReservation.
    """
    with transaction.atomic():
        stock_level = StockLevel.objects.select_for_update().get(spare_part=spare_part, stock_location=stock_location)
        if stock_level.quantity_on_hand < quantity:
            raise ValidationError(
                f"Only {stock_level.quantity_on_hand} of {spare_part.sku} available at {stock_location}, "
                f"requested {quantity}."
            )

        stock_level.quantity_on_hand -= quantity
        stock_level.save()

        usage = WorkOrderPartUsage.objects.create(
            work_order=work_order,
            spare_part=spare_part,
            quantity=quantity,
            date=timezone.localdate(),
            stock_location=stock_location,
        )

        # Best-effort: if this consumption matches an open reservation for
        # the same work order/part/location, mark it fulfilled rather than
        # leaving it dangling as RESERVED.
        reservation = (
            StockReservation.objects.select_for_update()
            .filter(
                stock_level=stock_level,
                work_order=work_order,
                status=StockReservation.Status.RESERVED,
                quantity__lte=quantity,
            )
            .order_by("reserved_at")
            .first()
        )
        if reservation:
            reservation.status = StockReservation.Status.FULFILLED
            reservation.save()

        return usage


def reserve_stock(*, work_order, spare_part, stock_location, quantity, user=None, notes=""):
    stock_level, _ = StockLevel.objects.get_or_create(spare_part=spare_part, stock_location=stock_location)
    return StockReservation.objects.create(
        stock_level=stock_level,
        work_order=work_order,
        quantity=quantity,
        reserved_by=user,
        notes=notes,
    )


def cancel_reservation(reservation):
    if reservation.status != StockReservation.Status.RESERVED:
        raise ValidationError(f"Cannot cancel a reservation that is already {reservation.status}.")
    reservation.status = StockReservation.Status.CANCELLED
    reservation.save()
    return reservation
