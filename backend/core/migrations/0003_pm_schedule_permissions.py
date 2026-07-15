"""Grants PMSchedule/PMScheduleGeneration permissions.

PM scheduling generates WorkOrders, so it's treated as part of the
Incident Manager's process ownership (same reasoning as that role owning
the failure-code taxonomy) rather than a new role - Admin also gets full
control; every other existing role gets view-only, consistent with how
they see other asset/work-order context. PMScheduleGeneration is
view-only for everyone (including Admin) since it's produced exclusively
by the generation service, never created by hand.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW_ONLY_ROLES = ["Management", "Lead Technician", "Technician", "Spare Parts Manager", "Asset Manager"]


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
                content_type__app_label="maintenance", codename=f"{action}_{model}"
            )
            group.permissions.add(perm)

    grant("Admin", "pmschedule", ["add", "change", "delete", "view"])
    grant("Admin", "pmschedulegeneration", ["view"])

    grant("Incident Manager", "pmschedule", ["add", "change", "view"])
    grant("Incident Manager", "pmschedulegeneration", ["view"])

    for role in VIEW_ONLY_ROLES:
        grant(role, "pmschedule", ["view"])
        grant(role, "pmschedulegeneration", ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="maintenance")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_asset_manager_and_superadmin_config"),
        ("maintenance", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
