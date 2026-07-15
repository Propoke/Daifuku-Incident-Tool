"""Grants permissions on core.Attachment (file/photo uploads).

Deliberately not symmetric add/delete for the operational roles: anyone
doing the work should be able to attach evidence (a photo of the failure,
the fix, a permit sign-off), but delete is restricted to Admin and
Incident Manager so an attachment isn't something "anyone can make
disappear" once uploaded - the model itself is mutable (unlike the
ImmutableModel-based audit records elsewhere), so this permission
boundary is what actually protects it.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW_ONLY_ROLES = ["Management", "Asset Manager", "Spare Parts Manager", "OEM"]
ADD_VIEW_ROLES = ["Lead Technician", "Technician"]


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
                content_type__app_label="core", codename=f"{action}_attachment"
            )
            group.permissions.add(perm)

    grant("Admin", ["add", "change", "delete", "view"])
    grant("Incident Manager", ["add", "change", "delete", "view"])
    for role in ADD_VIEW_ROLES:
        grant(role, ["add", "view"])
    for role in VIEW_ONLY_ROLES:
        grant(role, ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="core", codename__endswith="attachment")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_initial"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
