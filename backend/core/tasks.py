from celery import shared_task

from .notifications import notify_daily_digest


@shared_task(name="core.send_daily_digest")
def send_daily_digest_task():
    notify_daily_digest()
