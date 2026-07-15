"""Grants permissions on assets.AssetMeterReading (CMMS audit item #6 -
manual meter/usage readings that drive meter-based PM triggers).

No change/delete grants for anyone: it's an ImmutableModel like the other
logs in this repo - correcting a bad reading means logging a new one, not
editing history, since PMSchedule's meter trigger depends on this being a
reliable record. Add+view goes to the roles who'd actually log a reading;
everyone else gets view-only.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

ADD_VIEW_ROLES = ["Admin", "Lead Technician", "Technician"]
VIEW_ONLY_ROLES = ["Management", "Incident Manager", "Asset Manager", "Spare Parts Manager", "OEM"]


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
                content_type__app_label="assets", codename=f"{action}_assetmeterreading"
            )
            group.permissions.add(perm)

    for role in ADD_VIEW_ROLES:
        grant(role, ["add", "view"])
    for role in VIEW_ONLY_ROLES:
        grant(role, ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(
        content_type__app_label="assets", codename__endswith="assetmeterreading"
    )
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("assets", "0008_assetmeterreading"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
