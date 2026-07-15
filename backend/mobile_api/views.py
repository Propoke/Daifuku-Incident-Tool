from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from assets.access import scope_queryset_to_sites
from assets.models import Asset
from core.models import ChecklistItem
from inventory.models import StockLevel, StockLocation
from inventory.services import consume_stock, find_spare_part_by_code
from workorders.models import WorkOrder, WorkOrderChecklistResponse

from .permissions import HasModelPermission
from .serializers import (
    AssetLookupSerializer,
    ChecklistItemStatusSerializer,
    ChecklistResponseCreateSerializer,
    ConsumePartRequestSerializer,
    SparePartLookupSerializer,
    WorkOrderChecklistResponseSerializer,
    WorkOrderCommentSerializer,
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


class AssetLookupView(APIView):
    """GET /api/mobile/assets/lookup/?code=<scanned-tag>

    Resolves a scanned asset tag/QR code to the asset id so the PWA can
    hand off to the existing site-scoped asset history page
    (reporting.views.asset_history_view) instead of building a second
    asset-detail screen. Site-scoped like everything else here - a
    technician can't use this to discover an asset outside their access.
    """

    required_permission = "assets.view_asset"
    permission_classes = [HasModelPermission]

    def get(self, request):
        code = request.query_params.get("code")
        if not code:
            raise ValidationError({"code": "Query parameter 'code' is required."})
        queryset = scope_queryset_to_sites(request.user, Asset.objects.all(), "terminal__site_id")
        asset = queryset.filter(tag=code).first()
        if asset is None:
            return Response(
                {"detail": "No asset matches that tag, or it isn't at one of your sites."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AssetLookupSerializer(asset).data)


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


class WorkOrderCommentListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/mobile/workorders/<id>/comments/ - the phone
    equivalent of the WorkOrderCommentInline in the admin: view the
    running note thread on this specific ticket, and leave a quick note
    for the next shift without having to open the desktop admin."""

    serializer_class = WorkOrderCommentSerializer

    def get_permissions(self):
        self.required_permission = (
            "workorders.add_workordercomment"
            if self.request.method == "POST"
            else "workorders.view_workordercomment"
        )
        return [HasModelPermission()]

    def get_work_order(self):
        return get_object_or_404(_site_scoped_work_order_queryset(self.request.user), pk=self.kwargs["pk"])

    def get_queryset(self):
        return self.get_work_order().comments.select_related("author")

    def perform_create(self, serializer):
        serializer.save(work_order=self.get_work_order(), author=self.request.user)


class WorkOrderChecklistView(APIView):
    """GET/POST /api/mobile/workorders/<id>/checklist/ - the phone
    equivalent of WorkOrderChecklistResponseInline: view this ticket's
    checklist (empty if it has none) with the latest answer per item, and
    submit a new answer for one item. A new answer doesn't overwrite the
    old one (WorkOrderChecklistResponse is append-only) - it just becomes
    the new "latest" shown here, so a failed-then-fixed-then-passed step
    stays visible in the admin's full history.
    """

    def get_permissions(self):
        self.required_permission = (
            "workorders.add_workorderchecklistresponse"
            if self.request.method == "POST"
            else "workorders.view_workorderchecklistresponse"
        )
        return [HasModelPermission()]

    def get_work_order(self):
        return get_object_or_404(_site_scoped_work_order_queryset(self.request.user), pk=self.kwargs["pk"])

    def get(self, request, pk):
        work_order = self.get_work_order()
        if work_order.checklist_template_id is None:
            return Response([])

        latest_by_item = {}
        responses = WorkOrderChecklistResponse.objects.filter(work_order=work_order).select_related(
            "completed_by"
        )
        for response in responses:
            # Model orders by completed_at ascending, so the last one seen
            # per item in this loop is the latest.
            latest_by_item[response.checklist_item_id] = response

        rows = []
        for item in work_order.checklist_template.items.all():
            latest = latest_by_item.get(item.id)
            rows.append(
                {
                    "id": item.id,
                    "text": item.text,
                    "response_type": item.response_type,
                    "latest_response": latest.response_text if latest else None,
                    "latest_response_by": latest.completed_by.username if latest and latest.completed_by else None,
                    "latest_response_at": latest.completed_at if latest else None,
                }
            )
        return Response(ChecklistItemStatusSerializer(rows, many=True).data)

    def post(self, request, pk):
        work_order = self.get_work_order()
        serializer = ChecklistResponseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item = get_object_or_404(
            ChecklistItem,
            pk=serializer.validated_data["checklist_item_id"],
            template_id=work_order.checklist_template_id,
        )
        response = WorkOrderChecklistResponse.objects.create(
            work_order=work_order,
            checklist_item=item,
            response_text=serializer.validated_data["response_text"],
            completed_by=request.user,
        )
        return Response(WorkOrderChecklistResponseSerializer(response).data, status=status.HTTP_201_CREATED)


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
