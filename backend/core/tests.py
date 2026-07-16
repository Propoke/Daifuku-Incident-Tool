"""Tests for the daily notification digest (including the per-recipient
site-scoping regression guard), and site-scoped global search.

The SessionRefresh OIDC middleware redirects any request whose session
lacks OIDC markers - which force_login() never sets - so client-based
tests strip it via MIDDLEWARE_NO_OIDC.
"""

import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from assets.models import Asset, Customer, ServiceContract, Site, SparePart, Terminal
from inventory.models import StockLevel, StockLocation
from workorders.models import WorkOrder

User = get_user_model()

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
MIDDLEWARE_NO_OIDC = [m for m in settings.MIDDLEWARE if "SessionRefresh" not in m]


def breaching_asset(site, contract, customer, tag):
    term = Terminal.objects.create(site=site, code=f"{site.code}-T1")
    asset = Asset.objects.create(tag=tag, name=tag, terminal=term, service_contract=contract, owner_customer=customer)
    wo = WorkOrder.objects.create(asset=asset, work_order_type="CORRECTIVE", title=f"{tag} breach")
    WorkOrder.objects.filter(pk=wo.pk).update(created_at=timezone.now() - datetime.timedelta(hours=5))
    return asset


def low_stock_at(site, sku):
    loc = StockLocation.objects.create(site=site, code=f"{site.code}-LOC", name="loc")
    part = SparePart.objects.create(sku=sku, description="p")
    StockLevel.objects.create(spare_part=part, stock_location=loc, quantity_on_hand=0, min_quantity=5)


@override_settings(EMAIL_BACKEND=LOCMEM)
class DailyDigestScopingTests(TestCase):
    """Regression guard for the cross-site leak fixed in this branch: the
    digest must send each manager only their own site's data."""

    @classmethod
    def setUpTestData(cls):
        cls.cust = Customer.objects.create(code="C", name="c")
        cls.contract = ServiceContract.objects.create(
            customer=cls.cust, name="c", start_date=timezone.localdate(), sla_response_hours=1
        )
        cls.site_a = Site.objects.create(name="A", code="DA")
        cls.site_b = Site.objects.create(name="B", code="DB")
        breaching_asset(cls.site_a, cls.contract, cls.cust, "DA-1")
        breaching_asset(cls.site_b, cls.contract, cls.cust, "DB-1")
        low_stock_at(cls.site_a, "DA-SKU")
        low_stock_at(cls.site_b, "DB-SKU")

    def _digest(self):
        from core.notifications import notify_daily_digest

        mail.outbox = []
        notify_daily_digest()
        by_to = {}
        for m in mail.outbox:
            by_to.setdefault(m.to[0], []).append(m.body)
        return {to: "\n".join(bodies) for to, bodies in by_to.items()}

    def test_manager_sees_only_own_site(self):
        mgr_a = User.objects.create_user("mgra", email="a@x.com")
        mgr_a.groups.add(Group.objects.get(name="Management"), Group.objects.get(name="Spare Parts Manager"))
        self.site_a.allowed_users.add(mgr_a)
        mgr_b = User.objects.create_user("mgrb", email="b@x.com")
        mgr_b.groups.add(Group.objects.get(name="Management"), Group.objects.get(name="Spare Parts Manager"))
        self.site_b.allowed_users.add(mgr_b)

        bodies = self._digest()
        self.assertIn("DA-1", bodies["a@x.com"])
        self.assertNotIn("DB-1", bodies["a@x.com"])
        self.assertIn("DA-SKU", bodies["a@x.com"])
        self.assertNotIn("DB-SKU", bodies["a@x.com"])
        self.assertIn("DB-1", bodies["b@x.com"])
        self.assertNotIn("DA-1", bodies["b@x.com"])

    def test_oem_bypass_sees_everything(self):
        oem = User.objects.create_user("oem", email="oem@x.com")
        oem.groups.add(Group.objects.get(name="Management"), Group.objects.get(name="OEM"))
        bodies = self._digest()
        self.assertIn("DA-1", bodies["oem@x.com"])
        self.assertIn("DB-1", bodies["oem@x.com"])

    def test_no_access_manager_gets_nothing(self):
        mgr = User.objects.create_user("mgr", email="m@x.com")
        mgr.groups.add(Group.objects.get(name="Management"), Group.objects.get(name="Spare Parts Manager"))
        bodies = self._digest()
        self.assertNotIn("m@x.com", bodies)


@override_settings(MIDDLEWARE=MIDDLEWARE_NO_OIDC)
class GlobalSearchScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site_a = Site.objects.create(name="A", code="GA")
        cls.site_b = Site.objects.create(name="B", code="GB")
        term_a = Terminal.objects.create(site=cls.site_a, code="GA-T1")
        term_b = Terminal.objects.create(site=cls.site_b, code="GB-T1")
        cls.asset_a = Asset.objects.create(tag="GA-ASSET", name="a", terminal=term_a)
        cls.asset_b = Asset.objects.create(tag="GB-ASSET", name="b", terminal=term_b)

    def setUp(self):
        self.user = User.objects.create_user("searcher", password="pw", is_staff=True)
        self.site_a.allowed_users.add(self.user)
        self.client.force_login(self.user)

    def test_finds_accessible_asset(self):
        resp = self.client.get("/search/?q=GA-ASSET")
        # links to the asset's history page => it's an actual result row,
        # not just the query echoed back into the search box
        self.assertContains(resp, f"/reports/assets/{self.asset_a.id}/history/")

    def test_hides_cross_site_asset(self):
        resp = self.client.get("/search/?q=GB-ASSET")
        # the cross-site asset must not appear as a result row (its history
        # link), even though the query string itself is echoed in the box
        self.assertNotContains(resp, f"/reports/assets/{self.asset_b.id}/history/")
        self.assertContains(resp, "No matching assets.")

    def test_empty_query_renders_no_result_tables(self):
        resp = self.client.get("/search/")
        self.assertNotContains(resp, "<h2>Assets</h2>")
