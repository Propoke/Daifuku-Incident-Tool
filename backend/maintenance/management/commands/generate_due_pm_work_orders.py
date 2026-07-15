from django.core.management.base import BaseCommand

from maintenance.services import generate_due_work_orders


class Command(BaseCommand):
    help = "Create work orders for every due PM schedule (same logic the Celery beat task runs on a schedule)."

    def handle(self, *args, **options):
        created = generate_due_work_orders()
        if not created:
            self.stdout.write("No PM schedules due.")
            return
        for wo in created:
            self.stdout.write(self.style.SUCCESS(f"Created {wo} for asset {wo.asset.tag}"))
        self.stdout.write(self.style.SUCCESS(f"{len(created)} work order(s) created."))
