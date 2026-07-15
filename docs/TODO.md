# TODO / Backlog

Everything in `docs/cmms-audit.md`'s **Critical** and **Important** tiers is done — see that doc for what shipped and how each item was verified. What's left is the **Lower priority** tier: real gaps, but the audit's own assessment is that a pilot doesn't live or die on them. Tracked here as a plain backlog rather than left buried in the audit narrative.

None of these are scheduled. Pick them up whenever the corresponding pain actually shows up in practice, rather than pre-building for a need that hasn't materialized yet.

- [ ] **OEE (availability × performance × quality)** — standard in manufacturing-flavored CMMS. Needs the meter-reading infrastructure (`assets.AssetMeterReading`, shipped) as a prerequisite, which is already in place, but the OEE calculation/reporting itself isn't built.
- [ ] **Custom/ad-hoc report builder or CSV export** — the reporting dashboard is fixed-metric; exporting to a spreadsheet is a common ask once someone wants to slice the data their own way instead of just reading the dashboard.
- [ ] **Calendar export (iCal) for dispatch/PM schedules** — a quality-of-life add once the dispatch board (`teams.services`, `/dispatch/`) sees real day-to-day use.
- [ ] **Work-order relationships** — split into sub-tasks, duplicate-of, blocks/blocked-by. Matters more at higher ticket volume than a pilot will hit; `WorkOrder` has no self-referential relationship today.
- [ ] **Parts kitting** — pre-bundled sets of `SparePart`s for a common job type, so a technician doesn't have to scan each part individually. An efficiency feature on top of the existing scan-and-book flow, not a functionality gap.
- [ ] **Customer e-signature / sign-off in the portal** — relevant once field-service billing/proof-of-service actually matters to the business, not before. The portal (`portal` app) has no signature capture today.
- [ ] **In-app push notifications on the PWA** — same trigger points as the email notifications already built (`core.notifications`), once email proves out in practice and push becomes worth the extra complexity (service worker push subscriptions, a push provider).

## Also noted, not tracked as backlog items

Deliberate, documented tradeoffs made along the way - not forgotten, not silently accepted, just not worth a checkbox because they're either intentional for the current phase or already flagged with their own rationale elsewhere:

- **Object storage (MinIO) for attachments/media** — `core.Attachment` still writes to local disk. The infra plan (`docs/infrastructure-setup-plan.md`) has flagged MinIO since before any of this was built; `cmms/urls.py` now serves `/media/` outside `DEBUG` via `django.views.static.serve` as an explicit, documented stopgap for internal-network-only deployment, not a production-grade answer at real volume.
- **Permit-level checklist response capture** — `PermitToWork.checklist_template` exists for displaying a LOTO procedure, but only `WorkOrderChecklistResponse` actually records what a technician checked off. A permit-level equivalent is a known follow-up (see `docs/cmms-audit.md`, item #5).
- **PM-compliance reporting doesn't factor in checklist completion** — still measures "the ticket got closed," not "the checklist steps got done." Flagged alongside the checklist feature itself.
- **PWA offline queueing and real-device camera/`BarcodeDetector` testing** — see `docs/mobile-app-backlog.md`.
- **SLA auto-escalation / business-hours-aware clocks** — `workorders/sla.py` measures SLA status; it doesn't escalate or account for business hours.
- **A walk-up barcode consumption doesn't check active `StockReservation`s** — `inventory.services.consume_stock()` only checks physical `quantity_on_hand`, so it can eat into another work order's reservation. Noted on `StockReservation` itself.
