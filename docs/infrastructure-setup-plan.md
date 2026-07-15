# CMMS Infrastructure & Setup Plan

Builds on `docs/cmms-feature-draft.md`. Covers tech stack, deployment topology, sizing, networking, auth, backups, environments, and CI/CD for the CMMS described there.

## Confirmed Inputs

- **Resources**: Standard tier — 8 vCPU / 16GB RAM / 250GB+ disk on the Proxmox host, for the full app stack.
- **Topology**: Single VM running Docker Compose (not split across separate LXCs).
- **Backups**: Proxmox Backup Server (PBS) already in place for VM-level snapshots.
- **Identity**: Entra ID (Azure AD, cloud) is available — auth integration will use OIDC federation, not direct on-prem LDAP.

---

## Tech Stack Recommendation

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

One Proxmox **VM** (not LXC — avoids Docker-in-LXC nesting quirks, and a VM backs up cleanly as a single unit via PBS), running Docker Compose with these services:

```
┌─────────────────────────────────────────────────────┐
│ Proxmox VM (Debian/Ubuntu LTS, 8 vCPU/16GB/250GB+)   │
│                                                       │
│  traefik (reverse proxy, TLS)                        │
│    │                                                 │
│    ├─ django-app (Gunicorn, REST API + admin)        │
│    ├─ react-frontend (static build, served by app     │
│    │                  or a small nginx container)     │
│    ├─ celery-worker                                   │
│    ├─ celery-beat (scheduler: PM triggers, SLA checks) │
│    ├─ postgres (data volume on separate disk/mount)   │
│    ├─ redis (celery broker/result backend)            │
│    └─ minio (documents/photos, separate data volume)  │
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

- Internal DNS name (e.g. `cmms.internal.<domain>`), no port-forward to the internet.
- Firewall: inbound restricted to internal subnets/sites only.
- TLS terminated at Traefik even internally, using an internal CA-issued certificate if one exists, otherwise a self-signed cert trusted via internal distribution (avoids plaintext internal traffic — cheap to do now, painful to retrofit).
- **Important exception to "internal only"**: because Entra ID is cloud-hosted, the VM needs **outbound HTTPS** to Microsoft identity endpoints (`login.microsoftonline.com` and related) for the OIDC flow to work. Inbound stays internal-only; outbound to Microsoft's auth endpoints must be allowed through the firewall. Same applies later if a real email/SMTP relay or NTP is used.
- Designed so a later internet-exposure phase only adds a WAN-facing reverse proxy/VPN in front of the existing Traefik — no rearchitecture needed, per the original constraint.

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
2. Confirm internal DNS/certificate approach (internal CA available, or self-signed).
3. Decide staging environment budget/timing (can be deferred to just before Phase 1 build starts rather than provisioned immediately).
4. Once the above are confirmed, next step is provisioning the VM and standing up the base Docker Compose skeleton (Traefik + Postgres + empty Django project + Entra OIDC login) as the literal first "walking skeleton" milestone from the feature draft's risk audit.
