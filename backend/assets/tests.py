"""Tests for the site-scoping access-control foundation, the ImmutableModel
append-only guarantee, and Asset warranty / meter-reading behavior.

These encode invariants that were previously only checked by hand: site
access is the sole visibility gate and fails closed, and the append-only
models genuinely refuse edits/deletes at the model layer.
"""

import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from assets.access import get_accessible_site_ids, scope_queryset_to_sites
from assets.models import (
    Asset,
    AssetMeterReading,
    ConfigurationTemplate,
    ConfigurationVersion,
    Site,
    Terminal,
)

User = get_user_model()


class SiteScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site_a = Site.objects.create(name="A", code="A")
        cls.site_b = Site.objects.create(name="B", code="B")
        cls.term_a = Terminal.objects.create(site=cls.site_a, code="A-T1")
        cls.term_b = Terminal.objects.create(site=cls.site_b, code="B-T1")
        cls.asset_a = Asset.objects.create(tag="A-1", name="a", terminal=cls.term_a)
        cls.asset_b = Asset.objects.create(tag="B-1", name="b", terminal=cls.term_b)

    def test_superuser_is_unrestricted(self):
        su = User.objects.create_superuser("su", "su@x.com", "pw")
        self.assertIsNone(get_accessible_site_ids(su))

    def test_oem_group_is_unrestricted(self):
        u = User.objects.create_user("oem")
        u.groups.add(Group.objects.get(name="OEM"))
        self.assertIsNone(get_accessible_site_ids(u))

    def test_no_assignment_fails_closed(self):
        u = User.objects.create_user("nobody")
        self.assertEqual(get_accessible_site_ids(u), set())
        # and a scoped queryset returns nothing, not everything
        scoped = scope_queryset_to_sites(u, Asset.objects.all(), "terminal__site_id")
        self.assertEqual(scoped.count(), 0)

    def test_direct_user_assignment_scopes_to_that_site(self):
        u = User.objects.create_user("techa")
        self.site_a.allowed_users.add(u)
        self.assertEqual(get_accessible_site_ids(u), {self.site_a.id})
        scoped = scope_queryset_to_sites(u, Asset.objects.all(), "terminal__site_id")
        self.assertEqual(list(scoped), [self.asset_a])

    def test_group_assignment_scopes_to_that_site(self):
        grp = Group.objects.create(name="site-b-crew")
        self.site_b.allowed_groups.add(grp)
        u = User.objects.create_user("techb")
        u.groups.add(grp)
        self.assertEqual(get_accessible_site_ids(u), {self.site_b.id})
        scoped = scope_queryset_to_sites(u, Asset.objects.all(), "terminal__site_id")
        self.assertEqual(list(scoped), [self.asset_b])


class ImmutableModelTests(TestCase):
    def setUp(self):
        self.tmpl = ConfigurationTemplate.objects.create(code="T1", name="t")

    def test_configuration_version_cannot_be_edited(self):
        cv = ConfigurationVersion.objects.create(template=self.tmpl, version_label="v1", effective_date=timezone.localdate())
        cv.version_label = "v2"
        with self.assertRaises(ValidationError):
            cv.save()

    def test_configuration_version_cannot_be_deleted(self):
        cv = ConfigurationVersion.objects.create(template=self.tmpl, version_label="v1", effective_date=timezone.localdate())
        with self.assertRaises(ValidationError):
            cv.delete()

    def test_meter_reading_cannot_be_edited_or_deleted(self):
        site = Site.objects.create(name="S", code="S")
        term = Terminal.objects.create(site=site, code="S-T1")
        asset = Asset.objects.create(tag="S-1", name="s", terminal=term)
        r = AssetMeterReading.objects.create(asset=asset, meter_type="HOURS", value=10, recorded_at=timezone.now())
        r.value = 20
        with self.assertRaises(ValidationError):
            r.save()
        with self.assertRaises(ValidationError):
            r.delete()


class AssetWarrantyTests(TestCase):
    def setUp(self):
        site = Site.objects.create(name="W", code="W")
        term = Terminal.objects.create(site=site, code="W-T1")
        self.asset = Asset.objects.create(tag="W-1", name="w", terminal=term)

    def test_no_expiry_is_not_under_warranty(self):
        self.asset.warranty_expiry = None
        self.assertFalse(self.asset.is_under_warranty)

    def test_future_expiry_is_under_warranty(self):
        self.asset.warranty_expiry = timezone.localdate() + datetime.timedelta(days=1)
        self.assertTrue(self.asset.is_under_warranty)

    def test_today_is_inclusive(self):
        self.asset.warranty_expiry = timezone.localdate()
        self.assertTrue(self.asset.is_under_warranty)

    def test_past_expiry_is_not_under_warranty(self):
        self.asset.warranty_expiry = timezone.localdate() - datetime.timedelta(days=1)
        self.assertFalse(self.asset.is_under_warranty)


class MeterReadingHelperTests(TestCase):
    def test_latest_value_returns_most_recent(self):
        site = Site.objects.create(name="M", code="M")
        term = Terminal.objects.create(site=site, code="M-T1")
        asset = Asset.objects.create(tag="M-1", name="m", terminal=term)
        AssetMeterReading.objects.create(asset=asset, meter_type="HOURS", value=100, recorded_at=timezone.now() - datetime.timedelta(days=2))
        AssetMeterReading.objects.create(asset=asset, meter_type="HOURS", value=250, recorded_at=timezone.now())
        self.assertEqual(AssetMeterReading.latest_value(asset, "HOURS"), 250)
        self.assertIsNone(AssetMeterReading.latest_value(asset, "CYCLES"))
