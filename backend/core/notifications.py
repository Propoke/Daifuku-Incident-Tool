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
    as PM generation).

    Sent per-recipient and site-scoped: a manager assigned to one site
    only ever gets that site's breaches/low-stock, never another site's -
    the same visibility gate (assets.access) every other surface enforces.
    Management/Incident Manager/Spare Parts Manager are all site-scoped
    roles (not in access.BYPASS_GROUPS), so a global "everything to
    everyone" digest was the one place that leaked cross-site asset tags,
    ticket titles, and SKUs. Admin/OEM members of these groups get an
    unrestricted view (get_accessible_site_ids returns None), same as
    everywhere else.
    """
    from django.contrib.auth import get_user_model
    from django.db.models import F

    from assets.access import get_accessible_site_ids
    from inventory.models import StockLevel
    from workorders.sla import breached_open_work_orders

    User = get_user_model()

    def scoped_low_stock(user):
        queryset = StockLevel.objects.filter(quantity_on_hand__lte=F("min_quantity")).select_related(
            "spare_part", "stock_location__site"
        )
        site_ids = get_accessible_site_ids(user)
        if site_ids is not None:
            queryset = queryset.filter(stock_location__site_id__in=site_ids)
        return list(queryset)

    for user in User.objects.filter(
        groups__name__in=["Management", "Incident Manager"]
    ).exclude(email="").distinct():
        breached = breached_open_work_orders(user=user)
        if breached:
            lines = [f"{wo} - asset {wo.asset}" for wo in breached]
            _send(
                f"[CMMS] {len(breached)} work order(s) breaching SLA",
                "The following open work orders have breached their SLA target:\n\n" + "\n".join(lines),
                [user.email],
            )

    for user in User.objects.filter(groups__name="Spare Parts Manager").exclude(email="").distinct():
        low_stock = scoped_low_stock(user)
        if low_stock:
            lines = [
                f"{sl.spare_part.sku} @ {sl.stock_location} - {sl.quantity_on_hand} on hand (min {sl.min_quantity})"
                for sl in low_stock
            ]
            _send(
                f"[CMMS] {len(low_stock)} spare part(s) at or below reorder threshold",
                "The following stock levels are at or below their reorder threshold:\n\n" + "\n".join(lines),
                [user.email],
            )
