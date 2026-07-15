from rest_framework import serializers

from assets.models import Asset
from inventory.models import StockLevel
from workorders.models import WorkOrder, WorkOrderChecklistResponse, WorkOrderComment, WorkOrderPartUsage


class StockLevelSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="stock_location.name")
    location_code = serializers.CharField(source="stock_location.code")
    site = serializers.CharField(source="stock_location.site.name")
    quantity_reserved = serializers.IntegerField(read_only=True)
    quantity_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockLevel
        fields = [
            "id",
            "location_name",
            "location_code",
            "site",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
        ]


class SparePartLookupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    barcode = serializers.CharField(allow_null=True)
    description = serializers.CharField()
    stock_levels = StockLevelSerializer(many=True)


class AssetLookupSerializer(serializers.ModelSerializer):
    """Just enough for the PWA to redirect to the asset's (existing,
    site-scoped) history page - not a full asset representation."""

    class Meta:
        model = Asset
        fields = ["id", "tag", "name"]


class WorkOrderListSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="asset.tag")
    asset_name = serializers.CharField(source="asset.name")

    class Meta:
        model = WorkOrder
        fields = ["id", "title", "asset_tag", "asset_name", "work_order_type", "priority", "status", "due_date"]


class WorkOrderDetailSerializer(WorkOrderListSerializer):
    class Meta(WorkOrderListSerializer.Meta):
        fields = WorkOrderListSerializer.Meta.fields + [
            "description",
            "symptoms",
            "cause",
            "resolution",
            "actual_open_time",
            "actual_close_time",
            "checklist_template",
        ]


class ConsumePartRequestSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="Scanned barcode, or SKU as a fallback")
    stock_location_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class WorkOrderPartUsageSerializer(serializers.ModelSerializer):
    spare_part_sku = serializers.CharField(source="spare_part.sku")

    class Meta:
        model = WorkOrderPartUsage
        fields = ["id", "spare_part_sku", "quantity", "date", "stock_location"]


class WorkOrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WorkOrder.Status.choices)


class WorkOrderCommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True, default=None)

    class Meta:
        model = WorkOrderComment
        fields = ["id", "body", "author_username", "created_at"]
        read_only_fields = ["id", "author_username", "created_at"]


class ChecklistItemStatusSerializer(serializers.Serializer):
    """One row of GET /workorders/<id>/checklist/ - a checklist item plus
    whatever the latest response for it is, if any. Not a ModelSerializer:
    it's a merge of ChecklistItem and (at most one) WorkOrderChecklistResponse,
    not a single model instance."""

    id = serializers.IntegerField()
    text = serializers.CharField()
    response_type = serializers.CharField()
    latest_response = serializers.CharField(allow_null=True)
    latest_response_by = serializers.CharField(allow_null=True)
    latest_response_at = serializers.DateTimeField(allow_null=True)


class ChecklistResponseCreateSerializer(serializers.Serializer):
    checklist_item_id = serializers.IntegerField()
    response_text = serializers.CharField(max_length=300)


class WorkOrderChecklistResponseSerializer(serializers.ModelSerializer):
    completed_by_username = serializers.CharField(source="completed_by.username", read_only=True, default=None)

    class Meta:
        model = WorkOrderChecklistResponse
        fields = ["id", "checklist_item", "response_text", "completed_by_username", "completed_at"]
