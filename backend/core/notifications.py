"""Email notification hooks.

The assignment notification fires synchronously from WorkOrder.save() -
kept out of Celery deliberately, since "who gets told what" is simple
enough not to need a queue, and PM-auto-generated tickets already go
through the same save() path (see maintenance.services.generate_due_work_orders),
so this one hook covers both triggers. The daily digest (core.tasks) is the
piece that actually needs a schedule, since it has to look across all open
tickets/stock levels rather than react to a single save.

Every send is wrapped so a mail failure (unconfigured SMTP, unreachable
relay) never blocks the underlying save() or task - notifications are a
courtesy here, not a transactional guarantee.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send(subject, message, recipients):
    recipients = sorted({r for r in recipients if r})
    if not recipients:
        return
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    except Exception:
        logger.exception("Failed to send notification email: %s", subject)


def notify_work_order_assigned(work_order):
    recipients = []
    if work_order.assigned_to and work_order.assigned_to.email:
        recipients.append(work_order.assigned_to.email)
    if work_order.assigned_team:
        recipients += list(work_order.assigned_team.members.exclude(email="").values_list("email", flat=True))
    if not recipients:
        return

    url = f"{settings.CMMS_BASE_URL}/admin/workorders/workorder/{work_order.pk}/change/"
    subject = f"[CMMS] {work_order} assigned to you"
    message = (
        f"{work_order}\n"
        f"Type: {work_order.get_work_order_type_display()}  Priority: {work_order.get_priority_display()}\n"
        f"Asset: {work_order.asset}\n\n"
        f"{url}\n"
    )
    _send(subject, message, recipients)


def notify_daily_digest():
    """SLA-breach summary to Management/Incident Manager, low-stock summary
    to Spare Parts Manager. Called from core.tasks.send_daily_digest_task on
    an admin-editable Celery beat schedule (same DatabaseScheduler pattern
    as PM generation)."""
    from django.contrib.auth import get_user_model
    from django.db.models import F

    from inventory.models import StockLevel
    from workorders.sla import breached_open_work_orders

    User = get_user_model()

    breached = breached_open_work_orders()
    if breached:
        recipients = (
            User.objects.filter(groups__name__in=["Management", "Incident Manager"])
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )
        lines = [f"{wo} - asset {wo.asset}" for wo in breached]
        _send(
            f"[CMMS] {len(breached)} work order(s) breaching SLA",
            "The following open work orders have breached their SLA target:\n\n" + "\n".join(lines),
            recipients,
        )

    low_stock = list(
        StockLevel.objects.filter(quantity_on_hand__lte=F("min_quantity")).select_related(
            "spare_part", "stock_location__site"
        )
    )
    if low_stock:
        recipients = (
            User.objects.filter(groups__name="Spare Parts Manager")
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )
        lines = [
            f"{sl.spare_part.sku} @ {sl.stock_location} - {sl.quantity_on_hand} on hand (min {sl.min_quantity})"
            for sl in low_stock
        ]
        _send(
            f"[CMMS] {len(low_stock)} spare part(s) at or below reorder threshold",
            "The following stock levels are at or below their reorder threshold:\n\n" + "\n".join(lines),
            recipients,
        )
