from django import forms

from assets.access import scope_queryset_to_sites
from assets.models import Asset
from workorders.models import WorkOrder


class IssueReportForm(forms.ModelForm):
    """Self-service ticket submission - deliberately not gated on the
    workorders.add_workorder RBAC permission (only Technician/Lead
    Technician/Incident Manager/Admin have that). Any authenticated
    internal user should be able to report a problem; this form is the
    self-service exception to that permission, not a widening of it."""

    class Meta:
        model = WorkOrder
        fields = ["asset", "title", "description", "priority"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Asset.objects.filter(ownership=Asset.Ownership.INTERNAL)
        self.fields["asset"].queryset = scope_queryset_to_sites(user, queryset, "terminal__site_id")
