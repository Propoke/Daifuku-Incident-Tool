"""Seeds the Celery beat schedule that drives the daily SLA-breach/low-stock
notification digest (core.notifications.notify_daily_digest).

Uses django-celery-beat's DatabaseScheduler so the cadence is editable via
/admin/django_celery_beat/periodictask/ - no redeploy needed, matching the
pattern already used for PM auto-ticketing
(maintenance/migrations/0002_seed_pm_periodic_task.py).
"""

from django.db import migrations

TASK_NAME = "Send daily SLA/stock notification digest"


def create_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    db_alias = schema_editor.connection.alias

    schedule, _ = IntervalSchedule.objects.using(db_alias).get_or_create(every=1, period="days")
    PeriodicTask.objects.using(db_alias).get_or_create(
        name=TASK_NAME,
        defaults={
            "task": "core.send_daily_digest",
            "interval": schedule,
            "enabled": True,
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.using(schema_editor.connection.alias).filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_attachment_permissions"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_periodic_task, remove_periodic_task),
    ]
