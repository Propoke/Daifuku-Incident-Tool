"""Grants permissions on core.ChecklistTemplate/ChecklistItem (CMMS audit
item #5 - structured PM/permit checklists).

Designing a checklist (what steps exist, in what order) is a different
job from filling one out on a work order (workorders.WorkOrderChecklistResponse,
permissioned separately in workorders/migrations) - Admin and Asset
Manager get full add/change/delete/view here since they're the ones who'd
actually author a procedure; everyone else who might need to see what a
checklist contains gets view-only.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

FULL_ROLES = ["Admin", "Asset Manager"]
VIEW_ONLY_ROLES = ["Management", "Incident Manager", "Spare Parts Manager", "Lead Technician", "Technician", "OEM"]
MODELS = ["checklisttemplate", "checklistitem"]


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
                    content_type__app_label="core", codename=f"{action}_{model}"
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
        content_type__app_label="core", codename__iregex=r"_(checklisttemplate|checklistitem)$"
    )
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_checklisttemplate_checklistitem"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
