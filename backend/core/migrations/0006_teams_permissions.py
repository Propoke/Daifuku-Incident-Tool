"""Grants permissions on the new teams app (Team, Shift, ShiftHandoverNote).

Incident Manager gets the most control (add/change Team and Shift) as an
extension of already owning work assignment; Lead Technician can manage
Shift patterns and membership context for their own crew but not
restructure the Team itself; Technician can view and leave handover notes
(any team member ending a shift can leave one for the next); everyone else
who already sees other asset/work-order context gets view-only.
ShiftHandoverNote is add+view only for every role, including Admin -
matches its enforced immutability (assets.models.ImmutableModel).
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW_ONLY_ROLES = ["Management", "Asset Manager", "Spare Parts Manager", "OEM"]


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
                content_type__app_label="teams", codename=f"{action}_{model}"
            )
            group.permissions.add(perm)

    grant("Admin", "team", ["add", "change", "delete", "view"])
    grant("Admin", "shift", ["add", "change", "delete", "view"])
    grant("Admin", "shifthandovernote", ["add", "view"])

    grant("Incident Manager", "team", ["add", "change", "view"])
    grant("Incident Manager", "shift", ["add", "change", "view"])
    grant("Incident Manager", "shifthandovernote", ["add", "view"])

    grant("Lead Technician", "team", ["view"])
    grant("Lead Technician", "shift", ["add", "change", "view"])
    grant("Lead Technician", "shifthandovernote", ["add", "view"])

    grant("Technician", "team", ["view"])
    grant("Technician", "shift", ["view"])
    grant("Technician", "shifthandovernote", ["add", "view"])

    for role in VIEW_ONLY_ROLES:
        grant(role, "team", ["view"])
        grant(role, "shift", ["view"])
        grant(role, "shifthandovernote", ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="teams")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_oem_role"),
        ("teams", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
