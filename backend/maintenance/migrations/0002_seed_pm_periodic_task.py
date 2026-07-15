"""Seeds the Celery beat schedule that drives PM auto-ticketing.

Uses django-celery-beat's DatabaseScheduler so the cadence is editable via
/admin/django_celery_beat/periodictask/ - no redeploy needed to change how
often due PM schedules are checked, matching the admin-editable pattern
used elsewhere in this project.
"""

from django.db import migrations

TASK_NAME = "Generate due PM work orders"


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    db_alias = schema_editor.connection.alias

    schedule, _ = IntervalSchedule.objects.using(db_alias).get_or_create(every=1, period="days")
    PeriodicTask.objects.using(db_alias).get_or_create(
        name=TASK_NAME,
        defaults={
            "task": "maintenance.generate_due_pm_work_orders",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.using(schema_editor.connection.alias).filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
