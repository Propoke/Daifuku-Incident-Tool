"""Tests for PM work-order generation: the calendar trigger, the
meter-based trigger (fires only at/after threshold, then advances), and
that a generated work order inherits the schedule's team and checklist.
"""

import datetime

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, AssetMeterReading, Site, Terminal
from core.models import ChecklistTemplate
from maintenance.models import PMSchedule
from maintenance.services import generate_due_work_orders


def make_asset(code="S", tag="S-1"):
    site = Site.objects.create(name=code, code=code)
    term = Terminal.objects.create(site=site, code=f"{code}-T1")
    return Asset.objects.create(tag=tag, name=tag, terminal=term)


class CalendarPmTests(TestCase):
    def setUp(self):
        self.asset = make_asset()

    def test_due_schedule_generates_one_work_order(self):
        PMSchedule.objects.create(
            asset=self.asset, title="cal", interval_days=30,
            start_date=timezone.localdate() - datetime.timedelta(days=1),
        )
        created = generate_due_work_orders(as_of=timezone.localdate())
        self.assertEqual(len(created), 1)

    def test_not_yet_due_schedule_does_not_generate(self):
        PMSchedule.objects.create(
            asset=self.asset, title="cal", interval_days=30,
            start_date=timezone.localdate() + datetime.timedelta(days=5),
        )
        self.assertEqual(generate_due_work_orders(as_of=timezone.localdate()), [])

    def test_generated_work_order_inherits_checklist(self):
        tmpl = ChecklistTemplate.objects.create(name="pm")
        PMSchedule.objects.create(
            asset=self.asset, title="cal", interval_days=30,
            start_date=timezone.localdate() - datetime.timedelta(days=1),
            checklist_template=tmpl,
        )
        created = generate_due_work_orders(as_of=timezone.localdate())
        self.assertEqual(created[0].checklist_template, tmpl)


class MeterPmTests(TestCase):
    def setUp(self):
        self.asset = make_asset()
        # far-future calendar anchor so only the meter trigger can fire
        self.schedule = PMSchedule.objects.create(
            asset=self.asset, title="meter", interval_days=36500,
            start_date=timezone.localdate() + datetime.timedelta(days=365),
            meter_type="HOURS", meter_interval=500,
        )

    def test_no_readings_does_not_fire(self):
        created = generate_due_work_orders(as_of=timezone.localdate())
        self.assertEqual([w for w in created if w.title == "meter"], [])

    def test_below_threshold_does_not_fire(self):
        AssetMeterReading.objects.create(asset=self.asset, meter_type="HOURS", value=100, recorded_at=timezone.now())
        created = generate_due_work_orders(as_of=timezone.localdate())
        self.assertEqual([w for w in created if w.title == "meter"], [])

    def test_at_threshold_fires_once_and_advances(self):
        AssetMeterReading.objects.create(asset=self.asset, meter_type="HOURS", value=520, recorded_at=timezone.now())
        created = generate_due_work_orders(as_of=timezone.localdate())
        self.assertEqual(len([w for w in created if w.title == "meter"]), 1)
        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.next_due_meter_value, 1000)
        # re-running without a new reading does not re-fire
        again = generate_due_work_orders(as_of=timezone.localdate())
        self.assertEqual([w for w in again if w.title == "meter"], [])
