"""Grants safety.can_approve_permittowork (CMMS audit item #7 - permit
approval/sign-off workflow) to supervisor-level roles only. Distinct from
the ordinary add/change/delete/view permissions already granted on
PermitToWork - approving a permit is a deliberate supervisor action, not
something anyone who can edit a permit's other fields should be able to
do (see safety.admin.PermitToWorkAdmin's dedicated "Approve" action and
readonly approved_by/approved_at).
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

APPROVER_ROLES = ["Admin", "Management", "Incident Manager"]


def grant_permissions(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    for app_config in global_apps.get_app_configs():
        app_config.models_module = app_config.models_module or True
        create_permissions(app_config, apps=apps, verbosity=0, using=db_alias)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    try:
        perm = Permission.objects.using(db_alias).get(
            content_type__app_label="safety", codename="can_approve_permittowork"
        )
    except Permission.DoesNotExist:
        return

    for role in APPROVER_ROLES:
        try:
            group = Group.objects.using(db_alias).get(name=role)
        except Group.DoesNotExist:
            continue
        group.permissions.add(perm)


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(
        content_type__app_label="safety", codename="can_approve_permittowork"
    )
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0003_alter_permittowork_options_permittowork_approved_at_and_more"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
