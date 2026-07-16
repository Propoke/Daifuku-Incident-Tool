"""Tests for the customer portal's scoping: a portal user only ever sees
their own customer's tickets, and internal (non-portal) accounts are
denied. This is the second visibility gate (by owner_customer), separate
from internal site-scoping.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from assets.models import Asset, Customer, CustomerContact, Site, Terminal
from workorders.models import WorkOrder

User = get_user_model()
MIDDLEWARE_NO_OIDC = [m for m in settings.MIDDLEWARE if "SessionRefresh" not in m]


@override_settings(MIDDLEWARE=MIDDLEWARE_NO_OIDC)
class PortalScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="S", code="S")
        cls.term = Terminal.objects.create(site=cls.site, code="S-T1")
        cls.cust_x = Customer.objects.create(code="X", name="X")
        cls.cust_y = Customer.objects.create(code="Y", name="Y")
        cls.asset_x = Asset.objects.create(tag="X-1", name="x", terminal=cls.term, owner_customer=cls.cust_x)
        cls.asset_y = Asset.objects.create(tag="Y-1", name="y", terminal=cls.term, owner_customer=cls.cust_y)
        cls.wo_x = WorkOrder.objects.create(asset=cls.asset_x, work_order_type="CORRECTIVE", title="x ticket")
        cls.wo_y = WorkOrder.objects.create(asset=cls.asset_y, work_order_type="CORRECTIVE", title="y ticket")

    def setUp(self):
        self.user_x = User.objects.create_user("portalx", password="pw")
        CustomerContact.objects.create(user=self.user_x, customer=self.cust_x)

    def test_portal_home_shows_only_own_customer_tickets(self):
        self.client.force_login(self.user_x)
        resp = self.client.get("/portal/")
        # assert on the per-ticket detail links, not the titles - "y ticket"
        # is a substring of the "All my tickets" nav link, so title text is
        # an unreliable sentinel here
        self.assertContains(resp, f"/portal/tickets/{self.wo_x.pk}/")
        self.assertNotContains(resp, f"/portal/tickets/{self.wo_y.pk}/")

    def test_cannot_open_other_customers_ticket_by_url(self):
        self.client.force_login(self.user_x)
        resp = self.client.get(f"/portal/tickets/{self.wo_y.pk}/")
        self.assertEqual(resp.status_code, 404)

    def test_internal_account_without_contact_is_denied(self):
        internal = User.objects.create_user("staff", password="pw")
        self.client.force_login(internal)
        resp = self.client.get("/portal/")
        # portal_login_required raises PermissionDenied -> 403
        self.assertEqual(resp.status_code, 403)
