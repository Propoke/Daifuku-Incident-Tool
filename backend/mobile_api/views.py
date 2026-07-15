from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

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


class SparePartLookupView(APIView):
    """GET /api/mobile/spareparts/lookup/?code=<barcode-or-sku>

    Stock + location lookup by scanned code, for the mobile app's "what is
    this and where/how much do we have" screen.
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
        return Response(SparePartLookupSerializer(spare_part).data)


class MyWorkOrdersView(generics.ListAPIView):
    """GET /api/mobile/workorders/mine/ - "open tickets on their phone"."""

    required_permission = "workorders.view_workorder"
    permission_classes = [HasModelPermission]
    serializer_class = WorkOrderListSerializer

    def get_queryset(self):
        queryset = WorkOrder.objects.filter(assigned_to=self.request.user).exclude(status=WorkOrder.Status.CLOSED)
        return queryset.order_by("-priority", "due_date")


class WorkOrderDetailView(generics.RetrieveAPIView):
    required_permission = "workorders.view_workorder"
    permission_classes = [HasModelPermission]
    serializer_class = WorkOrderDetailSerializer
    queryset = WorkOrder.objects.all()


class WorkOrderStatusUpdateView(APIView):
    """POST /api/mobile/workorders/<id>/status/ - update status from the phone."""

    required_permission = "workorders.change_workorder"
    permission_classes = [HasModelPermission]

    def post(self, request, pk):
        work_order = get_object_or_404(WorkOrder, pk=pk)
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
        work_order = get_object_or_404(WorkOrder, pk=pk)
        serializer = ConsumePartRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        spare_part = find_spare_part_by_code(data["code"])
        if spare_part is None:
            return Response({"detail": "No spare part matches that code."}, status=status.HTTP_404_NOT_FOUND)
        stock_location = get_object_or_404(StockLocation, pk=data["stock_location_id"])

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
