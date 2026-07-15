"""Grants permissions on assets.Vendor (CMMS audit item #7 - real
supplier records with contact info/lead time, replacing the free-text
SparePart.supplier field, and the foundation for the PO workflow).

Admin/Spare Parts Manager author vendor records; everyone else who might
need to see supplier contact info gets view-only.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

FULL_ROLES = ["Admin", "Spare Parts Manager"]
VIEW_ONLY_ROLES = ["Management", "Incident Manager", "Asset Manager", "Lead Technician", "Technician", "OEM"]


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
        for action in actions:
            perm = Permission.objects.using(db_alias).get(content_type__app_label="assets", codename=f"{action}_vendor")
            group.permissions.add(perm)

    for role in FULL_ROLES:
        grant(role, ["add", "change", "delete", "view"])
    for role in VIEW_ONLY_ROLES:
        grant(role, ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="assets", codename__endswith="_vendor")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0010_vendor_sparepart_vendor"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
