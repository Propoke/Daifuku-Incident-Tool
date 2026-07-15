from django.urls import path

from . import views

urlpatterns = [
    path("spareparts/lookup/", views.SparePartLookupView.as_view(), name="mobile-sparepart-lookup"),
    path("workorders/mine/", views.MyWorkOrdersView.as_view(), name="mobile-workorders-mine"),
    path("workorders/<int:pk>/", views.WorkOrderDetailView.as_view(), name="mobile-workorder-detail"),
    path("workorders/<int:pk>/status/", views.WorkOrderStatusUpdateView.as_view(), name="mobile-workorder-status"),
    path(
        "workorders/<int:pk>/consume-part/", views.ConsumePartView.as_view(), name="mobile-workorder-consume-part"
    ),
]
