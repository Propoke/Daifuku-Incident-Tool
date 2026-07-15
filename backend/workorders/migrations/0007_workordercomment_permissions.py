"""Grants permissions on workorders.WorkOrderComment (the per-ticket note
thread - CMMS audit item #4).

No change/delete grants for anyone: WorkOrderComment is an ImmutableModel
(see assets.models.ImmutableModel) - the model layer itself refuses
edits/deletes after creation, so offering those permissions would just be
misleading UI that always errors. Admin/Incident Manager/Lead
Technician/Technician get add+view (people actively working tickets need
to be able to leave a note); everyone else gets view-only, matching the
add/view split already used for core.Attachment.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

ADD_VIEW_ROLES = ["Admin", "Incident Manager", "Lead Technician", "Technician"]
VIEW_ONLY_ROLES = ["Management", "Asset Manager", "Spare Parts Manager", "OEM"]


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
                content_type__app_label="workorders", codename=f"{action}_workordercomment"
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
        content_type__app_label="workorders", codename__endswith="workordercomment"
    )
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("workorders", "0006_workordercomment"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
