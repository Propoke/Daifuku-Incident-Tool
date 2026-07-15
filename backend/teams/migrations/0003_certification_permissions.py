"""Grants permissions on teams.Certification (CMMS audit item #7 -
technician skill/certification tracking, checked as a warning at
lockout/tagout permit-issuance time in safety.admin.PermitToWorkAdmin).

Admin/Management (an HR-adjacent role for this system) author
certification records; everyone else gets view-only - a certification
roster isn't sensitive, but only Admin/Management should be able to
attest someone is qualified.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

FULL_ROLES = ["Admin", "Management"]
VIEW_ONLY_ROLES = ["Incident Manager", "Asset Manager", "Spare Parts Manager", "Lead Technician", "Technician", "OEM"]


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
                content_type__app_label="teams", codename=f"{action}_certification"
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
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="teams", codename__endswith="certification")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0002_certification"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
