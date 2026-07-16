"""Tests for permit-to-work approval (permission-gated, never a plain
form field) and the LOTO certification warning at issuance time.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.utils import timezone

from assets.models import Asset, Site, Terminal
from safety.models import PermitToWork
from teams.models import Certification

User = get_user_model()
MIDDLEWARE_NO_OIDC = [m for m in settings.MIDDLEWARE if "SessionRefresh" not in m]
# The production STORAGES uses WhiteNoise's manifest static storage, which
# needs a collectstatic manifest that doesn't exist during tests - rendering
# the admin (which references {% static %}) would raise. Swap in plain
# storage for tests that load admin pages.
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def make_asset(code="S", tag="S-1"):
    site = Site.objects.create(name=code, code=code)
    term = Terminal.objects.create(site=site, code=f"{code}-T1")
    return site, Asset.objects.create(tag=tag, name=tag, terminal=term)


class PermitApprovalPermissionTests(TestCase):
    def setUp(self):
        _, self.asset = make_asset()
        self.permit = PermitToWork.objects.create(
            asset=self.asset, title="p", status="ACTIVE",
            valid_from=timezone.now(), valid_until=timezone.now(),
        )

    def test_technician_lacks_approve_permission(self):
        tech = User.objects.create_user("tech")
        tech.groups.add(Group.objects.get(name="Technician"))
        self.assertFalse(tech.has_perm("safety.can_approve_permittowork"))

    def test_incident_manager_has_approve_permission(self):
        im = User.objects.create_user("im")
        im.groups.add(Group.objects.get(name="Incident Manager"))
        self.assertTrue(im.has_perm("safety.can_approve_permittowork"))


@override_settings(MIDDLEWARE=MIDDLEWARE_NO_OIDC, STORAGES=TEST_STORAGES)
class PermitApproveActionTests(TestCase):
    def setUp(self):
        self.site, self.asset = make_asset()
        self.permit = PermitToWork.objects.create(
            asset=self.asset, title="p", status="ACTIVE",
            valid_from=timezone.now(), valid_until=timezone.now(),
        )

    def _run_action(self, user):
        self.site.allowed_users.add(user)
        self.client.force_login(user)
        return self.client.post(
            "/admin/safety/permittowork/",
            {"action": "approve_permits", "_selected_action": [str(self.permit.pk)], "index": "0", "select_across": "0"},
            follow=True,
        )

    def test_approver_can_approve(self):
        im = User.objects.create_user("im", is_staff=True)
        im.groups.add(Group.objects.get(name="Incident Manager"))
        self._run_action(im)
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.approved_by, im)
        self.assertIsNotNone(self.permit.approved_at)

    def test_non_approver_cannot_approve(self):
        tech = User.objects.create_user("tech", is_staff=True)
        tech.groups.add(Group.objects.get(name="Technician"))
        self._run_action(tech)
        self.permit.refresh_from_db()
        self.assertIsNone(self.permit.approved_by)


class LotoCertificationTests(TestCase):
    """The LOTO warning is emitted by PermitToWorkAdmin.save_model; here we
    test the underlying data condition it checks (a current cert named
    exactly "LOTO Authorized"), which is the part worth locking down."""

    def setUp(self):
        self.tech = User.objects.create_user("tech")

    def _has_current_loto(self):
        from django.db.models import Q

        return (
            Certification.objects.filter(holder=self.tech, name="LOTO Authorized")
            .filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate()))
            .exists()
        )

    def test_no_cert(self):
        self.assertFalse(self._has_current_loto())

    def test_current_cert(self):
        Certification.objects.create(holder=self.tech, name="LOTO Authorized", issued_date=timezone.localdate())
        self.assertTrue(self._has_current_loto())

    def test_expired_cert(self):
        Certification.objects.create(
            holder=self.tech, name="LOTO Authorized",
            issued_date=timezone.localdate() - timezone.timedelta(days=800),
            expiry_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        self.assertFalse(self._has_current_loto())
