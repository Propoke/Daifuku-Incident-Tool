from rest_framework.permissions import BasePermission


class HasModelPermission(BasePermission):
    """Ties a view to a Django model permission (e.g. "workorders.change_workorder"),
    read from the view's `required_permission` attribute - reuses the same
    RBAC permission table the admin already enforces instead of inventing a
    separate API-only permission scheme."""

    def has_permission(self, request, view):
        perm = getattr(view, "required_permission", None)
        if not perm:
            return True
        return bool(request.user and request.user.has_perm(perm))
