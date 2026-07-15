from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from assets.access import scope_queryset_to_sites
from inventory.models import StockLevel, StockLocation
from inventory.services import consume_stock, find_spare_part_by_code
from workorders.models import WorkOrder

from .permissions import HasModelPermission
from .serializers import (
    ConsumePartRequestSerializer,
    SparePartLookupSerializer,
    WorkOrderDetailSerializer,
    WorkOrderListSerializer,
    WorkOrderPartUsageSerializer,
    WorkOrderStatusUpdateSerializer,
)


class SparePartLookupResult:
    """Thin wrapper so SparePartLookupSerializer can render an already
    site-filtered stock_levels queryset instead of re-deriving it from the
    SparePart instance's (unfiltered) reverse relation."""

    def __init__(self, spare_part, stock_levels):
        self.id = spare_part.id
        self.sku = spare_part.sku
        self.barcode = spare_part.barcode
        self.description = spare_part.description
        self.stock_levels = stock_levels


def _site_scoped_work_order_queryset(user):
    return scope_queryset_to_sites(user, WorkOrder.objects.all(), "asset__terminal__site_id")


class SparePartLookupView(APIView):
    """GET /api/mobile/spareparts/lookup/?code=<barcode-or-sku>

    Stock + location lookup by scanned code, for the mobile app's "what is
    this and where/how much do we have" screen. The part catalog itself is
    global (not site-scoped); only the stock levels shown are restricted
    to the requesting user's accessible sites.
    """

    required_permission = "assets.view_sparepart"
    permission_classes = [HasModelPermission]

    def get(self, request):
        code = request.query_params.get("code")
        if not code:
            raise ValidationError({"code": "Query parameter 'code' is required."})
        spare_part = find_spare_part_by_code(code)
        if spare_part is None:
            return Response({"detail": "No spare part matches that code."}, status=status.HTTP_404_NOT_FOUND)

        stock_levels = spare_part.stock_levels.select_related("stock_location__site")
        stock_levels = scope_queryset_to_sites(request.user, stock_levels, "stock_location__site_id")

        result = SparePartLookupResult(spare_part, stock_levels)
        return Response(SparePartLookupSerializer(result).data)


class MyWorkOrdersView(generics.ListAPIView):
    """GET /api/mobile/workorders/mine/ - "open tickets on their phone"."""

    required_permission = "workorders.view_workorder"
    permission_classes = [HasModelPermission]
    serializer_class = WorkOrderListSerializer

    def get_queryset(self):
        queryset = _site_scoped_work_order_queryset(self.request.user)
        queryset = queryset.filter(assigned_to=self.request.user).exclude(status=WorkOrder.Status.CLOSED)
        return queryset.order_by("-priority", "due_date")


class WorkOrderDetailView(generics.RetrieveAPIView):
    required_permission = "workorders.view_workorder"
    permission_classes = [HasModelPermission]
    serializer_class = WorkOrderDetailSerializer

    def get_queryset(self):
        return _site_scoped_work_order_queryset(self.request.user)


class WorkOrderStatusUpdateView(APIView):
    """POST /api/mobile/workorders/<id>/status/ - update status from the phone."""

    required_permission = "workorders.change_workorder"
    permission_classes = [HasModelPermission]

    def post(self, request, pk):
        work_order = get_object_or_404(_site_scoped_work_order_queryset(request.user), pk=pk)
        serializer = WorkOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        work_order.status = serializer.validated_data["status"]
        work_order.save()
        return Response(WorkOrderDetailSerializer(work_order).data)


class ConsumePartView(APIView):
    """POST /api/mobile/workorders/<id>/consume-part/ - the barcode "book a
    part out of stock onto this ticket" action."""

    required_permission = "workorders.add_workorderpartusage"
    permission_classes = [HasModelPermission]

    def post(self, request, pk):
        work_order = get_object_or_404(_site_scoped_work_order_queryset(request.user), pk=pk)
        serializer = ConsumePartRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        spare_part = find_spare_part_by_code(data["code"])
        if spare_part is None:
            return Response({"detail": "No spare part matches that code."}, status=status.HTTP_404_NOT_FOUND)

        stock_location_qs = scope_queryset_to_sites(request.user, StockLocation.objects.all(), "site_id")
        stock_location = get_object_or_404(stock_location_qs, pk=data["stock_location_id"])

        try:
            usage = consume_stock(
                work_order=work_order,
                spare_part=spare_part,
                stock_location=stock_location,
                quantity=data["quantity"],
                user=request.user,
            )
        except StockLevel.DoesNotExist:
            return Response(
                {"detail": f"{spare_part.sku} isn't stocked at {stock_location}."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DjangoValidationError as exc:
            raise ValidationError({"detail": exc.messages}) from exc

        return Response(WorkOrderPartUsageSerializer(usage).data, status=status.HTTP_201_CREATED)
