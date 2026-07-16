"""Tests for WorkOrder.save() side effects (status-change logging,
actual_open_time auto-population, assignment notifications), the
append-only comment/checklist-response models, and SLA breach detection
with its site-scoping.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from assets.models import Asset, Customer, ServiceContract, Site, Terminal
from core.models import ChecklistItem, ChecklistTemplate
from teams.models import Team
from workorders.models import (
    WorkOrder,
    WorkOrderChecklistResponse,
    WorkOrderComment,
    WorkOrderStatusChange,
)
from workorders.sla import breached_open_work_orders

User = get_user_model()

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def make_asset(site_code="S", tag="S-1", **asset_kwargs):
    site = Site.objects.create(name=site_code, code=site_code)
    term = Terminal.objects.create(site=site, code=f"{site_code}-T1")
    asset = Asset.objects.create(tag=tag, name=tag, terminal=term, **asset_kwargs)
    return site, asset


class WorkOrderSaveTests(TestCase):
    def setUp(self):
        _, self.asset = make_asset()

    def test_new_work_order_logs_initial_status_change(self):
        wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        changes = wo.status_changes.all()
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().to_status, "OPEN")

    def test_status_transition_logs_a_change(self):
        wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        wo.status = "IN_PROGRESS"
        wo.save()
        self.assertTrue(wo.status_changes.filter(to_status="IN_PROGRESS").exists())

    def test_resave_without_status_change_does_not_log(self):
        wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        wo.title = "renamed"
        wo.save()
        self.assertEqual(wo.status_changes.count(), 1)

    def test_actual_open_time_auto_populates(self):
        wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        self.assertIsNotNone(wo.actual_open_time)

    def test_closing_sets_close_timestamps(self):
        wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        wo.status = "CLOSED"
        wo.save()
        self.assertIsNotNone(wo.closed_at)
        self.assertIsNotNone(wo.actual_close_time)


@override_settings(EMAIL_BACKEND=LOCMEM)
class WorkOrderAssignmentNotificationTests(TestCase):
    def setUp(self):
        _, self.asset = make_asset()
        self.tech = User.objects.create_user("tech", email="tech@x.com")

    def test_assigning_to_individual_emails_them(self):
        mail.outbox = []
        WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t", assigned_to=self.tech)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["tech@x.com"])

    def test_unrelated_resave_does_not_renotify(self):
        wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t", assigned_to=self.tech)
        mail.outbox = []
        wo.title = "renamed"
        wo.save()
        self.assertEqual(len(mail.outbox), 0)

    def test_no_assignment_no_email(self):
        mail.outbox = []
        WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        self.assertEqual(len(mail.outbox), 0)


class WorkOrderCommentImmutabilityTests(TestCase):
    def setUp(self):
        _, self.asset = make_asset()
        self.wo = WorkOrder.objects.create(asset=self.asset, work_order_type="CORRECTIVE", title="t")
        self.author = User.objects.create_user("author")

    def test_comment_cannot_be_edited_or_deleted(self):
        c = WorkOrderComment.objects.create(work_order=self.wo, author=self.author, body="hi")
        c.body = "edited"
        with self.assertRaises(ValidationError):
            c.save()
        with self.assertRaises(ValidationError):
            c.delete()


class ChecklistResponseTests(TestCase):
    def setUp(self):
        _, self.asset = make_asset()
        self.tmpl = ChecklistTemplate.objects.create(name="pm")
        self.item = ChecklistItem.objects.create(template=self.tmpl, order=1, text="check", response_type="PASS_FAIL")
        self.wo = WorkOrder.objects.create(asset=self.asset, work_order_type="PREVENTIVE", title="t", checklist_template=self.tmpl)
        self.user = User.objects.create_user("resp")

    def test_response_is_append_only(self):
        r = WorkOrderChecklistResponse.objects.create(
            work_order=self.wo, checklist_item=self.item, response_text="FAIL", completed_by=self.user
        )
        r.response_text = "PASS"
        with self.assertRaises(ValidationError):
            r.save()
        with self.assertRaises(ValidationError):
            r.delete()

    def test_corrected_answer_is_a_new_row(self):
        WorkOrderChecklistResponse.objects.create(work_order=self.wo, checklist_item=self.item, response_text="FAIL", completed_by=self.user)
        WorkOrderChecklistResponse.objects.create(work_order=self.wo, checklist_item=self.item, response_text="PASS", completed_by=self.user)
        self.assertEqual(WorkOrderChecklistResponse.objects.filter(work_order=self.wo, checklist_item=self.item).count(), 2)


class SlaBreachScopingTests(TestCase):
    def setUp(self):
        self.cust = Customer.objects.create(code="C", name="c")
        self.contract = ServiceContract.objects.create(
            customer=self.cust, name="c", start_date=timezone.localdate(), sla_response_hours=1
        )
        self.site_a, self.asset_a = make_asset("SA", "SA-1", service_contract=self.contract, owner_customer=self.cust)
        self.site_b, self.asset_b = make_asset("SB", "SB-1", service_contract=self.contract, owner_customer=self.cust)
        for asset in (self.asset_a, self.asset_b):
            wo = WorkOrder.objects.create(asset=asset, work_order_type="CORRECTIVE", title=f"{asset.tag} wo")
            WorkOrder.objects.filter(pk=wo.pk).update(created_at=timezone.now() - datetime.timedelta(hours=5))

    def test_unscoped_finds_all_breaches(self):
        self.assertEqual(len(breached_open_work_orders()), 2)

    def test_user_scoped_only_returns_own_site(self):
        u = User.objects.create_user("mgra")
        self.site_a.allowed_users.add(u)
        breached = breached_open_work_orders(user=u)
        self.assertEqual([wo.asset for wo in breached], [self.asset_a])

    def test_no_access_user_sees_no_breaches(self):
        u = User.objects.create_user("noone")
        self.assertEqual(breached_open_work_orders(user=u), [])
