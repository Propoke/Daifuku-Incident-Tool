from celery import shared_task

from .services import generate_due_work_orders


@shared_task(name="maintenance.generate_due_pm_work_orders")
def generate_due_pm_work_orders_task():
    created = generate_due_work_orders()
    return [wo.pk for wo in created]
