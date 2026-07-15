from django import forms

from assets.models import Asset
from workorders.models import WorkOrder


class PortalIssueReportForm(forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = ["asset", "title", "description", "priority"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset"].queryset = Asset.objects.filter(owner_customer=customer)
