"""Grants permissions on inventory.PurchaseOrder/PurchaseOrderLine (CMMS
audit item #7 - the "this part is on order, ETA Tuesday" workflow
StockLevel.needs_reorder never had a next step for).

Admin/Spare Parts Manager can create/edit/receive; everyone else who
might need visibility into what's on order gets view-only.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

FULL_ROLES = ["Admin", "Spare Parts Manager"]
VIEW_ONLY_ROLES = ["Management", "Incident Manager", "Asset Manager", "Lead Technician", "Technician", "OEM"]
MODELS = ["purchaseorder", "purchaseorderline"]


def grant_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    for app_config in global_apps.get_app_configs():
        app_config.models_module = app_config.models_module or True
        create_permissions(app_config, apps=apps, verbosity=0, using=db_alias)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    def grant(group_name, actions):
        try:
            group = Group.objects.using(db_alias).get(name=group_name)
        except Group.DoesNotExist:
            return
        for model in MODELS:
            for action in actions:
                perm = Permission.objects.using(db_alias).get(
                    content_type__app_label="inventory", codename=f"{action}_{model}"
                )
                group.permissions.add(perm)

    for role in FULL_ROLES:
        grant(role, ["add", "change", "delete", "view"])
    for role in VIEW_ONLY_ROLES:
        grant(role, ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(
        content_type__app_label="inventory", codename__iregex=r"_(purchaseorder|purchaseorderline)$"
    )
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_purchaseorder_purchaseorderline"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
