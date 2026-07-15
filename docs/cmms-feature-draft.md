# CMMS Platform — Feature Draft & High-Level Description

## Context

This is a greenfield project: a custom Computerized Maintenance Management System (CMMS), self-hosted on a Proxmox VM/LXC, reachable only on the internal network for now (internet exposure is a later phase). The system blends concepts from GLPI (asset/config management, ticketing/helpdesk) and ServiceMax (field service, entitlements, mobile dispatch), plus general CMMS best practice (PM scheduling, spare parts, work orders).

Confirmed scope:
- **Domain**: Material handling / automation equipment (conveyors, sorters, AS/RS-type systems), with a strong emphasis on **asset configuration management**: a `Site → Terminal → Asset` structure, reusable "Items" that can be combined into named "Configurations," configurations linked to machines, and the ability to change an individual machine's configuration independently of the template it came from.
- **Asset metadata**: firmware versions, software versions, install date, and other lifecycle/technical attributes.
- **PM planning** that auto-generates tickets/work orders.
- **Shift-based teams**: technicians organized into teams working shifts, with scheduling/handover awareness.
- **Field service / external customer capabilities** are in scope (ServiceMax-style), in addition to internal maintenance.
- **Scale**: Large — 100+ users, many sites.
- **Build approach**: Custom-built application (not a GLPI fork or off-the-shelf CMMS).

This document is the first deliverable: a feature list and high-level description to be refined before infrastructure/setup planning begins.

---

## High-Level Description

A custom, self-hosted CMMS for managing material handling and automation equipment across multiple sites. Its distinguishing feature is a **structured asset/configuration model**: physical locations break down into `Site → Terminal → Asset`, and each asset (machine) is built from a **Configuration** — a named, versionable bill of `Items` (modules/components/spare-part types) — which can be customized per individual machine without altering the shared template. On top of that sits standard CMMS machinery: preventive maintenance scheduling that auto-creates work orders, a helpdesk/ticketing layer for reactive issues, spare parts/inventory management, shift-based technician team scheduling, reporting/dashboards, and — because field service is in scope — customer/site entitlement tracking and mobile dispatch for technicians working off-site. Initially internal-network-only; designed so auth/exposure hardening can be layered on later without a rearchitecture.

---

## Feature List

### 1. Asset & Configuration Management *(core differentiator)*
- Hierarchical structure: **Site → Terminal → Asset** (extensible depth if needed later)
- **Item catalog**: reusable *logical* component/module definitions (the building blocks of a configuration) — every Item is orderable in principle, independent of whether it's currently stocked anywhere
- Each Item can map to **one or more Spare Part / SKU records** that fulfill it (approved alternates, different suppliers, etc.) — see §2
- **Configuration templates**: named sets of Items representing "how a machine type is built"
- **Configuration versioning**: each Configuration is versioned; every version has an **effective/changed-since date**, so an asset's current-config view shows "since [date]" at a glance, with full version history browsable
- Link a Configuration (version) to a machine/Asset; **override/customize the configuration per individual asset** without mutating the shared template
- Configuration change history (who changed what, when, previous vs. current version/date)
- **Asset ownership model**: distinguishes internally-owned assets (our Site/Terminal structure) from **customer-owned assets we service under contract** (linked to a Customer + Service Contract — see §6)
- Asset metadata: manufacturer, model, serial number, install date, warranty, criticality, status (installed/active/in-maintenance/decommissioned)
- **Firmware & software version tracking** per asset and/or per item, with "out of date" flagging against a target version
- Attach documents per asset/item/configuration (manuals, wiring diagrams, schematics, certificates)
- QR/barcode tagging for on-the-floor asset lookup and scanning
- Asset criticality classification (impacts PM priority & SLA)

### 2. Spare Parts & Inventory Management
- **Spare Part / SKU catalog**, each linked to the Item(s) it fulfills (many-to-many: one Item may have several approved SKUs; a SKU could theoretically fulfill more than one Item class)
- Stock levels per site/warehouse, min/max thresholds, reorder alerts — stock is a property of the Spare Part record, not the Item
- Items with no current stock anywhere remain **orderable** (procurement doesn't depend on existing inventory)
- Parts reservation against work orders
- Parts usage history and cost tracking
- Supplier/vendor records, purchase orders, receiving
- Inter-site stock transfers

### 3. Preventive Maintenance (PM) & Scheduling
- Time-based schedules (calendar recurrence)
- Usage/meter-based triggers (runtime hours, cycle counts) where equipment reports them
- PM checklist/procedure templates per asset type or configuration
- **Automatic ticket/work-order creation** from due PM schedules
- PM compliance tracking (on-time %, overdue backlog)
- Shift-aware scheduling — PM assigned to a team/shift, not just an individual

### 4. Work Order & Ticket Management
- Manual ticket creation (self-service, GLPI-style) and automatic creation (from PM, future monitoring/IoT hooks)
- Work order types: corrective, preventive, predictive, inspection, project
- Priority & SLA management with escalation
- Checklists/SOPs attached to work orders
- Labor & parts logging with cost roll-up
- Failure codes / root-cause tracking
- Status workflow with approvals
- Work order tied to the asset's **configuration state at time of work** (traceability)

### 5. Teams & Shift Management
- Teams and shift patterns (day/night/rotating)
- Technician skills/certifications
- Shift handover notes for continuity
- On-call/escalation rosters
- Dispatch/assignment board (calendar or drag-drop view)
- Labor time tracking against work orders

### 6. Field Service & External Customers *(ServiceMax-style)*
- Customer and customer-site records — **equipment is customer-owned**, serviced by us under contract (not our own asset)
- **Service contracts / entitlements / SLAs** per customer, tying a contract to the specific customer-owned assets it covers
- Contract-aware ticket/work-order handling (e.g., is this asset currently under an active contract; what SLA applies)
- Dispatch & scheduling for technicians visiting external customer sites
- Mobile-friendly technician experience: offline capability, digital signatures, photos, proof-of-service
- Customer-facing portal: submit tickets, view service/asset history
- Warranty tracking per customer asset

### 7. Helpdesk / Self-Service *(GLPI-style)*
- Self-service issue reporting for internal users and (if applicable) customers
- Knowledge base / FAQ
- Ticket categorization, SLA tracking, approval workflows
- Ticket-to-work-order conversion

### 8. Reporting & Analytics
- Dashboards: MTTR, MTBF, PM compliance %, open backlog, downtime by asset/site
- Configuration/firmware compliance reports (which machines are out of date)
- Cost analysis: labor, parts, downtime
- Custom report builder / CSV export
- Full audit trail (asset, configuration, and work order history)

### 9. Users, Access & Notifications
- Role-based access control (admin, planner, technician, requester, customer, viewer)
- Permission scoping by site — important at "many sites" scale
- **Microsoft Active Directory integration** (confirmed, Phase 1): authentication against AD, and group→role mapping so AD group membership can drive CMMS permissions
- Notifications: email, in-app, optionally SMS/push

### 10. Integration & Extensibility
- REST API
- Webhooks (e.g., ticket created, PM due, config changed)
- Bulk import/export (CSV/Excel) for onboarding large asset/parts datasets
- Barcode/QR scanning support
- Plugin/module architecture to add capabilities later without a rewrite
- Future hook point: PLC/SCADA/IoT monitoring integration for automatic ticket creation
- No ERP integration (confirmed out of scope) — purchase orders/receiving (§2) are handled natively, not synced to/from an ERP

### 11. Safety & Compliance *(candidate — confirm interest)*
- Permit-to-work / lockout-tagout logging
- Incident / near-miss reporting
- Calibration/inspection due-date tracking

---

## Suggested Phasing (for discussion, not final)

- **Phase 1 (MVP) — done**: Site/Terminal/Asset structure, Items & versioned Configurations (incl. per-asset override + dated history), Item↔SpareSKU mapping, asset metadata (firmware/software/install date), customer/asset ownership model, spare parts basics + stock/reservation logic, PM scheduling with auto ticket creation, work orders, RBAC with **Entra ID authentication**, shift/team model, and (beyond the original Phase 1 scope but built alongside it) site-scoped data access.
- **Phase 2**: Field service dispatch & mobile technician app (backlogged — see `docs/mobile-app-backlog.md`; the API it'll consume is already built), service contract/SLA enforcement logic, customer-facing portal, helpdesk self-service portal, reporting/dashboards, safety & compliance module.

---

## Confirmed Clarifications

1. **Item vs. spare part**: an **Item** is a *logical component* (e.g., "Drive Motor," "Barcode Scanner Module") — the thing a Configuration is built from. A **spare part** is the stocked, orderable representation of an Item at a given site. Every Item must be orderable even if not currently stocked anywhere; the "on stock at site X" marker is a property of the spare-part/inventory record, not the Item definition itself. Items and spare parts are related but distinct entities: Item (logical/catalog) → one or more Spare Part / SKU records (stock, supplier, orderability) that can fulfill it.
2. **Configuration versioning**: Configurations are formally versioned, and each version carries an effective/changed-since **date** so anyone viewing an asset can see at a glance since when it's been running its current configuration (and step back through prior versions/dates).
3. **Field service ownership model**: **customer-owned equipment**, serviced under **service contracts** held by us. The asset model needs a distinct "owner" (customer) vs. "serviced by us under contract X" relationship, separate from our own internally-owned Site/Terminal assets.
4. **AD integration**: Microsoft Active Directory integration is in scope (authentication and group/role mapping) for Phase 1.
5. **No ERP integration** — confirmed out of scope.
6. **Tech stack**: fully open, to be chosen on best-practice merit. Deferred to the infrastructure/setup planning phase — see the architectural risk audit below for constraints the feature set already implies.

Next step: infrastructure & setup planning (Proxmox VM/LXC sizing, DB choice, deployment approach, backup strategy, internal network access/auth).

---

## Architectural Risk Audit *(senior architect pass)*

A critical read of the plan above before any building starts. Ranked roughly by how expensive it is to get wrong.

### 1. The configuration engine is the load-bearing wall — treat it as such
Item → Configuration (versioned) → per-Asset override, with work orders referencing "config at time of service," is effectively a small **PLM/CMDB system**, not a CRUD feature. This is the highest-complexity, highest-risk part of the whole product, and almost everything else (PM triggers, firmware compliance reports, work order traceability) depends on its data model being right.
- **Risk**: if this is modeled as a mutable "current config" row with a bolted-on change log, you'll fight it forever — reports that ask "what was this asset running on March 3rd" become fragile joins against a log table instead of a first-class query.
- **Recommendation**: model it as **append-only/event-sourced from day one** — `ConfigurationVersion` rows are immutable once created; an asset's "current configuration" is a derived pointer, not a mutable field. Design and validate this data model (with a few real machines' actual BOMs) *before* writing PM automation or reporting on top of it — those are easy to bolt on later; the config core is not.

### 2. Don't build two asset systems by accident
Internally-owned assets (Site → Terminal → Asset) and customer-owned assets under contract are related-but-distinct. There's a real risk of ending up with parallel `InternalAsset` and `CustomerAsset` tables/code paths that duplicate configuration, firmware tracking, and work-order logic.
- **Recommendation**: one `Asset` entity with a required **ownership/context** attribute (internal vs. customer-owned-under-contract) and a location hierarchy that can point either into your Site→Terminal tree or a Customer→CustomerSite tree. Contract/SLA data attaches to the ownership record, not to a forked asset type. This keeps configuration versioning, firmware tracking, and reporting single-implementation for both cases.

### 3. Site/customer data segregation needs to be enforced at the query layer, not the UI
At 100+ users and "many sites," plus customer-owned equipment under contract, there's a real multi-tenancy-like requirement even though it's a single internal deployment: **Customer A's technicians/portal users must never be able to see Customer B's assets, tickets, or contract terms**, and internal site-scoped roles need the same enforcement across sites.
- **Recommendation**: bake row-level/site-scoped authorization into the data access layer (e.g., a query-scoping middleware or DB row-security policy) rather than relying on the frontend to only show the right data. This is much cheaper to design in from the start than to retrofit once dozens of screens exist.
- **Status: implemented for internal sites** — `assets.access` (query-scoping at the application layer, not DB-level row security) restricts Asset/WorkOrder/PMSchedule/StockLocation/StockLevel/StockReservation to a user's assigned site(s), enforced in both the Django admin and the mobile API. Sites are assignable to individual users or to a whole Group. An "OEM" group and the existing "Admin" group bypass it entirely (see everything); anyone else with no site assignment sees nothing (fail closed) until assigned one. **Not yet covered**: customer-owned assets (via CustomerSite, not Site) aren't scoped by this mechanism at all — the customer-segregation half of this recommendation is still open, relevant once the field-service/customer-portal work happens.

### 4. AD integration shapes the auth architecture — decide the mechanism early
"AD integration" can mean several very different things: direct LDAP bind, Kerberos/SSO, or federation via ADFS/Entra ID (SAML/OIDC). Each has different implications for the customer-facing portal in particular (external customer users almost certainly should *not* be AD accounts).
- **Recommendation**: use AD (via LDAP or, better, OIDC/SAML federation if Entra ID is available) for **internal users only**; keep customer/portal users as a separate identity path (local accounts or a separate IdP) from day one. Trying to force external customers through internal AD is a common and painful mistake.

### 5. Phase 1 as currently scoped is still a lot for a first release
Bundling the versioned configuration engine + PM automation + spare parts + AD auth + shift/team scheduling into one MVP is ambitious, and the config engine (§1 above) is the piece most likely to need rework once real usage patterns show up.
- **Recommendation**: consider an even narrower **walking skeleton** ahead of full Phase 1 — Asset/Configuration CRUD with versioning + AD login + manual work orders only, populated with a handful of real machines — to validate the data model with actual users before building PM automation, shift logic, and reporting on top of it. Cheap to adjust the config model before dependents exist; expensive after.

### 6. Gaps not yet in the feature list, worth a decision (even if the decision is "not now")
- **Document/file storage strategy**: manuals, schematics, and photos (§1, §6) don't belong as DB blobs at this scale — plan for object storage (e.g., S3-compatible/MinIO) from the start.
- **Configuration/version audit trail retention & immutability**: if service contracts (§6) have compliance implications, config and work-order history may need formal retention guarantees, not just "there's a history table."
- **Mobile offline sync conflicts**: §6 calls for offline-capable field technician mobile use — offline edits from two techs on the same work order will conflict; decide a conflict-resolution rule (e.g., last-write-wins with a visible warning, or lock-on-checkout) before building offline sync, not after.
- **SLA/escalation rules engine**: §6/§4 mention SLA management and escalation — this tends to grow into its own subsystem (breach detection, notification timing, business-hours-aware clocks). Worth scoping explicitly rather than treating as "a field on the ticket."
- **Backup/DR and environments**: given customer contract data will live in this system, a backup/restore policy and at least a staging environment should be a stated requirement before go-live.
- **Search at scale**: with many sites and large asset/parts catalogs, "find this asset/part fast" (by name, tag, serial, barcode) needs to be a first-class capability, not an afterthought query.

### What this changes in the plan
No features are being cut based on this audit — it's sequencing and data-modeling guidance for the *build*, not a scope change. The one concrete recommendation worth carrying into infra/setup planning: **treat the Asset/Configuration/Ownership data model as the first thing to design and validate, ahead of committing to a full Phase 1 feature freeze.**
