"""Seeds the CMMS's RBAC roles as Django Groups with model permissions.

Role design (standard RBAC: least privilege, separation of duties between
those who record work and those who own/approve process or master data):

- Admin: full control over all domain data plus user/group management.
- Management: read-only oversight across everything - no operational
  editing rights, matching the standard "oversight, not execution" RBAC
  pattern for an executive/management role.
- Incident Manager: owns the WorkOrder/incident process end-to-end
  (create, reassign, close, manage the failure-code taxonomy) but doesn't
  edit asset/configuration master data or spare-parts inventory - those
  are read-only context.
- Lead Technician: supervises a crew's work orders and can correct their
  logged labor/parts entries; same read-only view of asset/configuration
  master data as a Technician.
- Technician: works assigned incidents, logs their own labor and parts
  usage, views (doesn't edit) asset/configuration/spare-parts data.
- Spare Parts Manager: owns the Item/SparePart catalog and inventory;
  everything else is read-only context.

No role here owns the Site/Terminal/Customer/ConfigurationTemplate/
ConfigurationVersion/Asset master data for write access except Admin -
none of the six requested roles is a natural fit for that (e.g. an
"Asset Manager"/"Configuration Engineer" role), so it's deliberately
Admin-only until such a role is requested.

ConfigurationVersion, ConfigurationVersionItem, and
AssetConfigurationAssignment are add-only (no "change"/"delete" granted,
even to Admin) to match their enforced immutability at the model layer
(assets.models.ImmutableModel). WorkOrderStatusChange is view-only for
everyone, including Admin: it's created exclusively by WorkOrder.save()
and manual creation would bypass that tracking.
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

_ASSET_VIEW_ONLY = [
    "site",
    "terminal",
    "customer",
    "customersite",
    "servicecontract",
    "item",
    "sparepart",
    "configurationtemplate",
    "configurationversion",
    "configurationversionitem",
    "asset",
    "assetconfigurationassignment",
]

ROLE_PERMISSIONS = {
    "Admin": {
        "assets": {
            "site": ["add", "change", "delete", "view"],
            "terminal": ["add", "change", "delete", "view"],
            "customer": ["add", "change", "delete", "view"],
            "customersite": ["add", "change", "delete", "view"],
            "servicecontract": ["add", "change", "delete", "view"],
            "item": ["add", "change", "delete", "view"],
            "sparepart": ["add", "change", "delete", "view"],
            "configurationtemplate": ["add", "change", "delete", "view"],
            "configurationversion": ["add", "view"],
            "configurationversionitem": ["add", "view"],
            "asset": ["add", "change", "delete", "view"],
            "assetconfigurationassignment": ["add", "view"],
        },
        "workorders": {
            "failurecode": ["add", "change", "delete", "view"],
            "workorder": ["add", "change", "delete", "view"],
            "workorderstatuschange": ["view"],
            "workorderlaborentry": ["add", "change", "delete", "view"],
            "workorderpartusage": ["add", "change", "delete", "view"],
        },
        "auth": {
            "user": ["add", "change", "delete", "view"],
            "group": ["add", "change", "delete", "view"],
        },
    },
    "Management": {
        "assets": {model: ["view"] for model in _ASSET_VIEW_ONLY},
        "workorders": {
            model: ["view"]
            for model in [
                "failurecode",
                "workorder",
                "workorderstatuschange",
                "workorderlaborentry",
                "workorderpartusage",
            ]
        },
    },
    "Incident Manager": {
        "assets": {model: ["view"] for model in _ASSET_VIEW_ONLY},
        "workorders": {
            "failurecode": ["add", "change", "view"],
            "workorder": ["add", "change", "view"],
            "workorderstatuschange": ["view"],
            "workorderlaborentry": ["view"],
            "workorderpartusage": ["view"],
        },
    },
    "Lead Technician": {
        "assets": {model: ["view"] for model in _ASSET_VIEW_ONLY},
        "workorders": {
            "failurecode": ["add", "view"],
            "workorder": ["add", "change", "view"],
            "workorderstatuschange": ["view"],
            "workorderlaborentry": ["add", "change", "view"],
            "workorderpartusage": ["add", "change", "view"],
        },
    },
    "Technician": {
        "assets": {model: ["view"] for model in _ASSET_VIEW_ONLY},
        "workorders": {
            "failurecode": ["view"],
            "workorder": ["add", "change", "view"],
            "workorderstatuschange": ["view"],
            "workorderlaborentry": ["add", "view"],
            "workorderpartusage": ["add", "view"],
        },
    },
    "Spare Parts Manager": {
        "assets": {
            "item": ["add", "change", "delete", "view"],
            "sparepart": ["add", "change", "delete", "view"],
            "site": ["view"],
            "terminal": ["view"],
            "customer": ["view"],
            "customersite": ["view"],
            "servicecontract": ["view"],
            "configurationtemplate": ["view"],
            "configurationversion": ["view"],
            "configurationversionitem": ["view"],
            "asset": ["view"],
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


def create_roles(apps, schema_editor):
    # Permissions are normally created by a post_migrate signal that fires
    # only after the whole `migrate` run finishes, so on a fresh database
    # they don't exist yet at this point in the run. Create them explicitly
    # first so the Permission lookups below don't fail.
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


def remove_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.using(schema_editor.connection.alias).filter(name__in=ROLE_PERMISSIONS.keys()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("assets", "0001_initial"),
        ("workorders", "0002_workorder_actual_close_time_and_more"),
    ]

    operations = [
        migrations.RunPython(create_roles, remove_roles),
    ]
