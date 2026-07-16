# CMMS Infrastructure & Setup Plan

Builds on `docs/cmms-feature-draft.md`. Covers tech stack, deployment topology, sizing, networking, auth, backups, environments, and CI/CD for the CMMS described there.

## Confirmed Inputs

- **Resources**: Standard tier — 8 vCPU / 16GB RAM / 250GB+ disk on the Proxmox host, for the full app stack.
- **Topology**: Single VM running Docker Compose (not split across separate LXCs).
- **Backups**: Proxmox Backup Server (PBS) already in place for VM-level snapshots.
- **Identity**: Entra ID (Azure AD, cloud) is available — auth integration will use OIDC federation, not direct on-prem LDAP.

---

## Tech Stack Recommendation

> **As-built note (kept current):** the backend, both auth paths, PostgreSQL, Celery/Redis, and Traefik are all built and in the repo. **Two rows below are still planned, not built:** the **React frontend** was never started — the actual UI is Django admin + a handful of custom Django templates (`/reports/`, `/dispatch/`, `/portal/`, helpdesk) + the installable technician **PWA** at `/app/` (vanilla JS, no React); and **object storage (MinIO)** is not wired up — attachments/media currently live on local disk (served by WhiteNoise/`django.views.static`, see `docs/proxmox-deployment.md` and `docs/TODO.md`). The rationale in those two rows still stands as the intended direction; they just haven't happened yet.

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python + Django + Django REST Framework** | Django admin gives a working CRUD UI for Assets/Items/Configurations almost for free — directly supports the "walking skeleton" recommendation in the feature draft's risk audit (validate the config data model with real data before building a polished frontend). Mature migrations, mature OIDC libraries, strong ecosystem for a small team to maintain long-term. |
| Auth (internal) | **mozilla-django-oidc** against Entra ID | Entra ID is available, so OIDC federation is used instead of direct LDAP bind — simpler, more secure, no service account holding directory-bind credentials. |
| Auth (customer portal) | Separate local-account identity path (Django's own auth, scoped to a `customer_portal` user type) | Per the risk audit: external customer users should not be forced through internal AD/Entra tenant. Kept as a distinct auth path from day one. |
| Database | **PostgreSQL 16** | Relational integrity for the versioned Configuration/Item/Asset model; row-level security available natively, which directly supports the audit's site/customer data-segregation requirement. |
| Background jobs | **Celery + Redis** | Drives PM schedule evaluation → auto ticket creation, SLA breach checks/escalation, notifications — all naturally scheduled/async work, not request-cycle work. |
| Object storage | **MinIO** (S3-compatible, self-hosted) via `django-storages` | Manuals, schematics, photos don't belong as DB blobs at this scale (flagged in the risk audit). S3-compatible API keeps the door open to a managed alternative later without code changes. |
| Frontend | **React + TypeScript**, consuming the DRF API | Django admin covers Phase 0 (internal data entry/validation); a dedicated React frontend is built for the real Phase 1 UI and later for a PWA-capable offline-friendly technician experience. |
| Reverse proxy / TLS | **Traefik** | Terminates TLS even for internal-only access (avoid plaintext HTTP internally), simple Docker-label-based routing for the Compose stack, easy to extend when internet exposure is added later. |

This isn't the only viable stack (Node/NestJS or Java/Spring Boot were both considered), but it's the one that best fits: a small team self-hosting a long-lived internal tool, an admin-heavy early validation phase, and Entra ID as the identity provider.

---

## Deployment Topology

One Proxmox **VM** (not LXC — avoids Docker-in-LXC nesting quirks, and a VM backs up cleanly as a single unit via PBS), running Docker Compose. The diagram below is the **target** topology; rows marked *(planned)* aren't in the current `docker-compose.yml` yet (see the as-built note above). What actually ships today is: `traefik`, `backend` (Gunicorn — REST API + admin + the Django-template UIs + the PWA, static served by WhiteNoise), `celery-worker`, `celery-beat`, `postgres`, `redis`.

```
┌─────────────────────────────────────────────────────┐
│ Proxmox VM (Debian/Ubuntu LTS, 8 vCPU/16GB/250GB+)   │
│                                                       │
│  traefik (reverse proxy, TLS)                        │
│    │                                                 │
│    ├─ django-app (Gunicorn, REST API + admin + PWA)  │
│    ├─ react-frontend  ...................(planned)    │
│    ├─ celery-worker                                   │
│    ├─ celery-beat (scheduler: PM triggers, digest)    │
│    ├─ postgres (data volume on separate disk/mount)   │
│    ├─ redis (celery broker/result backend)            │
│    └─ minio (documents/photos) .........(planned)     │
└─────────────────────────────────────────────────────┘
```

Indicative resource split within the VM (adjust once real usage is observed):
- Django app + Gunicorn workers: ~2 vCPU / 4GB
- Celery worker + beat: ~1 vCPU / 2GB
- PostgreSQL: ~2 vCPU / 4–6GB
- Redis: ~0.5 vCPU / 1GB
- MinIO: ~1 vCPU / 2GB (disk grows independently as documents/photos accumulate — give it its own volume so it can be resized without touching the Postgres volume)
- Traefik + OS overhead: remainder

---

## Networking & Access

- Internal DNS name in a Cloudflare-managed zone (e.g. `cmms.internal.<company-domain>`), no port-forward to the internet — the hostname only needs a DNS record, it doesn't need to be internet-routable.
- Firewall: inbound restricted to internal subnets/sites only.
- **TLS: publicly-trusted certificate via Let's Encrypt, issued through Traefik's native ACME DNS-01 challenge against Cloudflare** — decided over a self-signed cert or a private/internal CA (step-ca, AD CS). Rationale: at 100+ users across many sites, plus a customer-facing portal and field technicians on personal devices on the roadmap, trust distribution for a private CA becomes its own ongoing burden, whereas a public CA cert is trusted everywhere by default with zero client-side setup. Renewal is fully automatic (Traefik handles it via the ACME DNS-01 flow), and this is the same mechanism the system will use once it's actually internet-facing — no TLS rework needed for that later phase, just a firewall/routing change. See `README.md` for the concrete setup (Cloudflare-scoped API token, ACME email, staging vs. production Let's Encrypt endpoint).
- **Outbound exceptions to "internal only"**: the VM needs outbound HTTPS to (1) Microsoft's Entra identity endpoints (`login.microsoftonline.com` and related) for the OIDC login flow, and (2) Let's Encrypt's ACME API plus the Cloudflare API for certificate issuance/renewal. Inbound stays internal-only in both cases; only these specific outbound destinations need firewall allowances. Same pattern would apply later if a real email/SMTP relay or NTP service is added.
- Designed so a later internet-exposure phase only adds a WAN-facing route to the existing Traefik — no rearchitecture and no TLS migration needed, per the original constraint.

---

## Authentication

- **Internal users**: Entra ID via OIDC (`mozilla-django-oidc`). Entra security groups map to CMMS roles (admin/planner/technician/requester/viewer) via group-claim mapping — mirrors the AD group→role approach from the feature draft, just via Entra instead of on-prem AD.
- **Customer portal users**: separate local accounts (or a lightweight dedicated IdP later), never mixed into the internal Entra tenant. Enforced as a distinct Django user type/permission scope, not just a UI distinction.
- **Row-level segregation**: Postgres row-level security (or equivalent query-scoping in the Django ORM layer) enforces that a given user only ever sees their site(s) / their customer's assets — enforced at the data-access layer, not just hidden in the UI, per the risk audit.

---

## Backup & Disaster Recovery

- **VM-level**: PBS handles nightly (or per your existing PBS schedule) full VM snapshot backups — the baseline DR layer, already in place.
- **Application-level, in addition**: nightly `pg_dump` (or continuous WAL archiving if point-in-time recovery matters for contract/compliance data) written to a location PBS also captures, or better, to a separate target so backups don't live solely on the same host as the VM they're backing up. This gives finer-grained restore (a specific table/timestamp) than a full VM restore.
- MinIO data volume included in the VM snapshot; consider periodic `mc mirror` to a second location if document loss would be costly.
- Document and test a restore procedure once the stack is running — an untested backup is not a backup.

---

## Environments

The Standard sizing above is scoped for **production**. Recommend a separate, smaller environment for staging:
- A lightweight VM or LXC (e.g. 2 vCPU / 4GB) running the same Docker Compose stack with its own Postgres/Redis/MinIO, seeded with representative (non-real-customer) data.
- Primary purpose: rehearse Django migrations against the versioned Configuration/Item/Asset schema before they hit production — this is the piece flagged in the risk audit as most likely to need iteration, so a safe place to test schema changes matters disproportionately here.
- This is additive to the resources already confirmed for production; flagging it now so it can be budgeted rather than discovered as a gap later.

---

## CI/CD & Deploy Workflow

- GitHub Actions on this repo: run tests/lint on every push and PR.
- Deploy step: since the target is internal-network-only, a public GitHub-hosted runner can't reach the VM directly. Two options:
  - **Self-hosted GitHub Actions runner** on the internal network (registered to this repo), so Actions can `docker compose pull && up -d` on push to `main` — enables real CI/CD.
  - **Manual/scripted deploy** (a single `deploy.sh` invoked by hand or via SSH) for now, upgrading to a self-hosted runner once the workflow is proven.
- Recommend starting with the manual script (lower setup cost, matches "internal network only for now") and adding the self-hosted runner once the stack has stabilized.

---

## Open Items / Next Steps

1. Confirm base OS image for the VM (e.g. Debian 12 or Ubuntu 22.04/24.04 LTS) — either works fine with Docker; pick whichever matches existing Proxmox templates/patching conventions.
2. ~~Confirm internal DNS/certificate approach~~ — done: Let's Encrypt via Cloudflare DNS-01 (see Networking & Access above).
3. Decide staging environment budget/timing (can be deferred to just before Phase 1 build starts rather than provisioned immediately).
4. ~~Stand up the base Docker Compose skeleton~~ — done: Traefik + Postgres + Django + Entra OIDC login is in the repo (`docker-compose.yml`, `backend/`), verified locally (migrations, health check, OIDC redirect flow). Not yet verified as a full `docker compose up` stack (this sandbox blocks Docker Hub pulls) — worth a quick smoke test on the actual Proxmox VM before trusting it.
