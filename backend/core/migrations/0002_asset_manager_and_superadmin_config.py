"""Adds the Asset Manager role and locks configuration editing to superadmins.

Asset Manager owns the physical/organizational asset master data that
0001_create_roles.py left as Admin-only (none of the six original roles
was a natural fit for it): Site, Terminal, Customer, CustomerSite,
ServiceContract, Asset. Everything else - including the configuration
subsystem - stays read-only for this role.

Separately: the configuration assigned to an asset (ConfigurationTemplate,
ConfigurationVersion, ConfigurationVersionItem, AssetConfigurationAssignment)
is now editable by actual Django superusers only - not even the Admin
group. That's enforced in code (assets.admin.SuperuserOnlyEditMixin), not
just by permissions, so it can't be loosened by mis-configuring a group;
this migration removes the now-inaccurate add/change/delete grants from
Admin so the permission table matches what the UI actually allows.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

ROLE_PERMISSIONS = {
    "Asset Manager": {
        "assets": {
            "site": ["add", "change", "delete", "view"],
            "terminal": ["add", "change", "delete", "view"],
            "customer": ["add", "change", "delete", "view"],
            "customersite": ["add", "change", "delete", "view"],
            "servicecontract": ["add", "change", "delete", "view"],
            "asset": ["add", "change", "delete", "view"],
            "item": ["view"],
            "sparepart": ["view"],
            "configurationtemplate": ["view"],
            "configurationversion": ["view"],
            "configurationversionitem": ["view"],
            "assetconfigurationassignment": ["view"],
        },
        "workorders": {
            "failurecode": ["view"],
            "workorder": ["view"],
            "workorderstatuschange": ["view"],
            "workorderlaborentry": ["view"],
            "workorderpartusage": ["view"],
        },
    },
}

# These were granted to Admin by 0001_create_roles.py; the config-editing
# surface is now superuser-only in code (assets/admin.py), so keep the
# permission table honest by revoking them here.
ADMIN_PERMS_TO_REVOKE = [
    ("assets", "add_configurationtemplate"),
    ("assets", "change_configurationtemplate"),
    ("assets", "delete_configurationtemplate"),
    ("assets", "add_configurationversion"),
    ("assets", "add_configurationversionitem"),
    ("assets", "add_assetconfigurationassignment"),
]


def create_roles(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    for app_config in global_apps.get_app_configs():
        app_config.models_module = app_config.models_module or True
        create_permissions(app_config, apps=apps, verbosity=0, using=db_alias)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for group_name, apps_perms in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.using(db_alias).get_or_create(name=group_name)
        for app_label, models_perms in apps_perms.items():
            for model, actions in models_perms.items():
                for action in actions:
                    codename = f"{action}_{model}"
                    perm = Permission.objects.using(db_alias).get(
                        content_type__app_label=app_label, codename=codename
                    )
                    group.permissions.add(perm)

    try:
        admin_group = Group.objects.using(db_alias).get(name="Admin")
    except Group.DoesNotExist:
        return
    revoke_perms = Permission.objects.using(db_alias).filter(
        content_type__app_label__in=[app for app, _ in ADMIN_PERMS_TO_REVOKE],
        codename__in=[codename for _, codename in ADMIN_PERMS_TO_REVOKE],
    )
    admin_group.permissions.remove(*revoke_perms)


def reverse_roles(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    Group = apps.get_model("auth", "Group")
    Group.objects.using(db_alias).filter(name="Asset Manager").delete()

    Permission = apps.get_model("auth", "Permission")
    try:
        admin_group = Group.objects.using(db_alias).get(name="Admin")
    except Group.DoesNotExist:
        return
    restore_perms = Permission.objects.using(db_alias).filter(
        content_type__app_label__in=[app for app, _ in ADMIN_PERMS_TO_REVOKE],
        codename__in=[codename for _, codename in ADMIN_PERMS_TO_REVOKE],
    )
    admin_group.permissions.add(*restore_perms)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_create_roles"),
    ]

    operations = [
        migrations.RunPython(create_roles, reverse_roles),
    ]
