from rest_framework import serializers

from inventory.models import StockLevel
from workorders.models import WorkOrder, WorkOrderPartUsage


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
