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
        # Site access is the only gate now - any asset at the user's site
        # is reportable, internally owned or customer-owned alike.
        self.fields["asset"].queryset = scope_queryset_to_sites(user, Asset.objects.all(), "terminal__site_id")
