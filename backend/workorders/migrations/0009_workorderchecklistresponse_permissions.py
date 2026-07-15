"""Grants permissions on workorders.WorkOrderChecklistResponse (CMMS audit
item #5 - what a technician actually entered against a PM/permit
checklist on a specific work order).

No change/delete grants for anyone: like WorkOrderComment, this is an
ImmutableModel - the model layer refuses edits/deletes after creation, so
those permissions would just be misleading UI that always errors.
Add+view goes to the roles who actually do the work; everyone else gets
view-only.
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
                content_type__app_label="workorders", codename=f"{action}_workorderchecklistresponse"
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
        content_type__app_label="workorders", codename__endswith="workorderchecklistresponse"
    )
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("workorders", "0008_workorder_checklist_template_and_more"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
