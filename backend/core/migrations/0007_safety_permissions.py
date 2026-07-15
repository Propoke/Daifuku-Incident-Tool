"""Grants permissions on the new safety app (PermitToWork, IncidentReport).

No dedicated "Safety Officer" role exists among the roles built so far, so
this fits into the existing set rather than inventing a new one: Incident
Manager gets full add/change (closest existing owner of "handling things
that go wrong"); Lead Technician and Technician can report incidents and
raise permits (anyone doing the work needs to be able to do both); everyone
else who already sees other asset/work-order context gets view-only.
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
                content_type__app_label="safety", codename=f"{action}_{model}"
            )
            group.permissions.add(perm)

    grant("Admin", "permittowork", ["add", "change", "delete", "view"])
    grant("Admin", "incidentreport", ["add", "change", "delete", "view"])

    grant("Incident Manager", "permittowork", ["add", "change", "view"])
    grant("Incident Manager", "incidentreport", ["add", "change", "view"])

    for role in ["Lead Technician", "Technician"]:
        grant(role, "permittowork", ["add", "change", "view"])
        grant(role, "incidentreport", ["add", "change", "view"])

    for role in VIEW_ONLY_ROLES:
        grant(role, "permittowork", ["view"])
        grant(role, "incidentreport", ["view"])


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    db_alias = schema_editor.connection.alias
    perms = Permission.objects.using(db_alias).filter(content_type__app_label="safety")
    for group in Group.objects.using(db_alias).all():
        group.permissions.remove(*perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_teams_permissions"),
        ("safety", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
