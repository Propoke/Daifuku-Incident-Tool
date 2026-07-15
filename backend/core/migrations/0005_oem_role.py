"""Adds the OEM group.

Same view-only permission set as Management across every domain app - "see
everything" is expressed here as broad view access, matching how every
other role's visibility was defined. What actually makes OEM special is
handled outside the Django permission system entirely: assets.access
treats membership in the "OEM" group (alongside "Admin") as exempt from
site-scoping, so OEM sees every site's data while every other role is
restricted to its assigned site(s).
"""

from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations

VIEW_ONLY_MODELS = {
    "assets": [
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
    ],
    "workorders": [
        "failurecode",
        "workorder",
        "workorderstatuschange",
        "workorderlaborentry",
        "workorderpartusage",
    ],
    "maintenance": ["pmschedule", "pmschedulegeneration"],
    "inventory": ["stocklocation", "stocklevel", "stockreservation"],
}


def create_role(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    for app_config in global_apps.get_app_configs():
        app_config.models_module = app_config.models_module or True
        create_permissions(app_config, apps=apps, verbosity=0, using=db_alias)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group, _ = Group.objects.using(db_alias).get_or_create(name="OEM")
    for app_label, models in VIEW_ONLY_MODELS.items():
        for model in models:
            perm = Permission.objects.using(db_alias).get(content_type__app_label=app_label, codename=f"view_{model}")
            group.permissions.add(perm)


def remove_role(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.using(schema_editor.connection.alias).filter(name="OEM").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_inventory_permissions"),
    ]

    operations = [
        migrations.RunPython(create_role, remove_role),
    ]
