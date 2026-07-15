"""Grants permissions on the new inventory app (StockLocation, StockLevel,
StockReservation).

Ownership follows the same reasoning as the Item/SparePart catalog:
Spare Parts Manager owns stock levels and locations; reservations are add-
able by Spare Parts Manager and Lead Technician (planning parts for a
crew's upcoming job); everyone else who already sees asset/work-order
context gets view-only, consistent with the rest of the RBAC design.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW_ONLY_ROLES = ["Management", "Incident Manager", "Technician", "Asset Manager"]


def grant_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    for app_config in global_apps.get_app_configs():
        app_config.models_module = app_config.models_module or True
        create_permissions(app_config, apps=apps, verbosity=0, using=db_alias)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    def grant(group_name, model, actions):
        try:
            group = Group.objects.using(db_alias).get(name=group_name)
        except Group.DoesNotExist:
            return
        for action in actions:
            perm = Permission.objects.using(db_alias).get(
                content_type__app_label="inventory", codename=f"{action}_{model}"
            )
            group.permissions.add(perm)

    grant("Admin", "stocklocation", ["add", "change", "delete", "view"])
    grant("Admin", "stocklevel", ["add", "change", "delete", "view"])
    grant("Admin", "stockreservation", ["add", "change", "delete", "view"])

    grant("Spare Parts Manager", "stocklocation", ["add", "change", "delete", "view"])
    grant("Spare Parts Manager", "stocklevel", ["add", "change", "delete", "view"])
    grant("Spare Parts Manager", "stockreservation", ["add", "change", "view"])

    grant("Lead Technician", "stocklocation", ["view"])
    grant("Lead Technician", "stocklevel", ["view"])
    grant("Lead Technician", "stockreservation", ["add", "view"])

    for role in VIEW_ONLY_ROLES:
        grant(role, "stocklocation", ["view"])
        grant(role, "stocklevel", ["view"])
        grant(role, "stockreservation", ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="inventory")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_pm_schedule_permissions"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
