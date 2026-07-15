"""Grants permissions on assets.CustomerContact (customer portal accounts).

Mirrors the existing Customer/CustomerSite pattern: Admin and Asset
Manager get full control (they already own the Customer/CustomerSite
master data this extends), everyone else who already sees customer
context gets view-only.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW_ONLY_ROLES = [
    "Management",
    "Incident Manager",
    "Lead Technician",
    "Technician",
    "Spare Parts Manager",
    "OEM",
]


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
            perm = Permission.objects.using(db_alias).get(
                content_type__app_label="assets", codename=f"{action}_customercontact"
            )
            group.permissions.add(perm)

    grant("Admin", ["add", "change", "delete", "view"])
    grant("Asset Manager", ["add", "change", "delete", "view"])
    for role in VIEW_ONLY_ROLES:
        grant(role, ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="assets", codename__endswith="customercontact")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_safety_permissions"),
        ("assets", "0007_customercontact"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
