# Daifuku Incident Tool — CMMS

Custom, self-hosted CMMS for maintaining material handling/automation equipment, blending GLPI (asset/config management, ticketing) and ServiceMax (field service, entitlements) concepts. See:

- [`docs/cmms-feature-draft.md`](docs/cmms-feature-draft.md) — feature list, high-level description, and the architectural risk audit.
- [`docs/infrastructure-setup-plan.md`](docs/infrastructure-setup-plan.md) — tech stack, deployment topology, networking, auth, and backup strategy.
- [`docs/mobile-app-backlog.md`](docs/mobile-app-backlog.md) — the technician PWA (`/app/`): what shipped, and the known gaps (offline support, real-device camera testing).

Started as a **walking skeleton** (Traefik + PostgreSQL + Django with Entra ID login) to validate the deployment shape and auth flow before building on top of it. Now also includes: the Asset/Configuration data model with per-asset ownership tracking and a full history view (`assets`, `reporting/assets/<id>/history/`), Work Orders/incidents (`workorders`), RBAC roles + site-scoped data access (`core`, `assets/access.py` — site access is the sole visibility gate, independent of who owns an asset), teams and shifts (`teams`), PM scheduling with Celery-driven auto-ticketing (`maintenance`), stock/reservation tracking (`inventory`), an installable technician PWA (`/app/`, `pwa` app, now with an asset-tag scan mode alongside the part-barcode scan) and the API behind it (`mobile_api`), an MTTR/PM-compliance/SLA/cost dashboard (`reporting`), SLA measurement against service contracts (`workorders/sla.py`), permit-to-work/incident reporting (`safety`), helpdesk self-service for any employee (`/report-issue/`, `/my-tickets/`), a team-based dispatch board (`/dispatch/`, `teams/services.py`), and a customer portal with local-account login (`/portal/`, `portal` app) scoped to each customer's own assets/tickets via `Asset.owner_customer` — separate from the internal Entra/site-scoping system entirely, generic file/photo attachments (`core.Attachment`) on assets, work orders, permits, and incident reports, email notifications (`core.notifications`) on work order assignment and a daily SLA-breach/low-stock digest, an append-only comment thread on each work order (`workorders.WorkOrderComment`) visible/postable from both the admin and the PWA, structured PM/permit checklists (`core.ChecklistTemplate`/`ChecklistItem`, `workorders.WorkOrderChecklistResponse`) copied from a `PMSchedule` onto its generated work orders and filled in from either the admin or the PWA, meter/usage-based PM triggers (`assets.AssetMeterReading`, manually logged) alongside the existing calendar-based ones, whichever fires first, and a vendor/purchase-order/receiving workflow (`assets.Vendor`, `inventory.PurchaseOrder`/`PurchaseOrderLine`) so `StockLevel.needs_reorder` finally has a next step.

## Stack

Django + Django REST Framework, PostgreSQL, Traefik (TLS termination via Let's Encrypt DNS-01 through Cloudflare), Entra ID via `mozilla-django-oidc`, Celery + Redis + `django-celery-beat` for scheduled jobs (currently: PM auto-ticketing). Full infra rationale in the infra plan doc above, including why a public CA cert on a split-horizon hostname was chosen over a self-signed or internal CA.

## Backend-only local iteration (no TLS/Traefik needed)

For quick day-to-day backend work, run Django directly against a local Postgres — this is how the walking skeleton itself was verified:

```
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
createdb cmms  # or point POSTGRES_HOST/POSTGRES_* at any local Postgres
cd backend
DJANGO_SECRET_KEY=dev POSTGRES_DB=cmms POSTGRES_USER=<you> POSTGRES_HOST=localhost \
  ../.venv/bin/python manage.py migrate
DJANGO_SECRET_KEY=dev POSTGRES_DB=cmms POSTGRES_USER=<you> POSTGRES_HOST=localhost \
  ../.venv/bin/python manage.py runserver
```

`/healthz` and `/admin/` work immediately; `/` will redirect into the Entra OIDC flow, which needs real `OIDC_*` values (see below) to complete.

## Running the full stack (Traefik + TLS)

1. Create a scoped Cloudflare API token for the DNS-01 challenge:
   - Cloudflare dashboard → **My Profile → API Tokens → Create Token → Custom token**
   - Permissions: `Zone` / `DNS` / `Edit`
   - Zone Resources: scope to the specific zone that owns `CMMS_HOSTNAME` (not "All zones") — least privilege, this token can only edit DNS TXT records for that one zone
   - Do **not** use the Cloudflare global API key — it's account-wide and far broader than Traefik needs
   - Copy the generated token; you won't be able to view it again after leaving the page

2. Copy the env template and fill in real values:
   ```
   cp .env.example .env
   ```
   - `DJANGO_SECRET_KEY`: generate one, e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `POSTGRES_PASSWORD`: any value for local/staging, a real secret for production
   - `CMMS_HOSTNAME`: a real hostname in the Cloudflare zone you scoped the token to above (can resolve internally-only — it doesn't need to be internet-reachable, DNS-01 doesn't require that)
   - `ACME_EMAIL`: a real address Let's Encrypt can send expiry/problem notices to
   - `CF_DNS_API_TOKEN`: the token from step 1
   - `ACME_CA_SERVER`: leave as the production Let's Encrypt endpoint, or point at `https://acme-staging-v02.api.letsencrypt.org/directory` while testing to avoid production rate limits
   - `OIDC_TENANT_ID` / `OIDC_RP_CLIENT_ID` / `OIDC_RP_CLIENT_SECRET`: from an Entra ID app registration (redirect URI `https://<CMMS_HOSTNAME>/oidc/callback/`)

3. Build and start the stack:
   ```
   docker compose up -d --build
   ```
   Traefik requests and renews the cert automatically via Cloudflare's DNS API on first boot — no manual cert handling. `traefik/acme/acme.json` (gitignored — it holds the account key and issued certs) is created with restrictive permissions on first run.

4. Verify:
   - `curl https://<CMMS_HOSTNAME>/healthz` → `{"status": "ok"}` (real cert, no `-k` needed)
   - `https://<CMMS_HOSTNAME>/admin/` — Django admin (create a superuser first: `docker compose exec backend python manage.py createsuperuser`)
   - `https://<CMMS_HOSTNAME>/` — redirects to Entra ID login if not authenticated
   - `https://<CMMS_HOSTNAME>/app/` — the technician PWA; needs the real HTTPS cert (browsers require a secure context for service workers and camera access — `localhost` is exempt for local dev, but any other hostname over plain HTTP won't work)

## PM scheduling

`celery-worker` and `celery-beat` (see `docker-compose.yml`) turn due `PMSchedule`s into `WorkOrder`s automatically, on the cadence set in `/admin/django_celery_beat/periodictask/` (daily by default — editable there, no redeploy needed). To run it manually instead of waiting for the schedule: `python manage.py generate_due_pm_work_orders` (works with just Postgres, no Celery/Redis required for this manual path). A schedule can carry a calendar interval, a meter interval (hours/cycles, driven by manually-logged `AssetMeterReading`s), or both — whichever fires first generates the work order.

## Email notifications

`WorkOrder.save()` emails whoever a ticket gets assigned to (an individual and/or every member of an assigned team) — this fires for both direct reassignment in the admin and PM auto-generated tickets, since both go through the same save path. A separate daily digest (`core.send_daily_digest`, same admin-editable `PeriodicTask` pattern as PM scheduling) emails an SLA-breach summary to Management/Incident Manager and a low-stock summary to Spare Parts Manager. `DJANGO_EMAIL_BACKEND` defaults to the console backend (emails are logged, not actually sent) so this works out of the box locally — set the `EMAIL_*` vars in `.env` to point at a real SMTP relay for production.

## Deploying

Target environment: a single Proxmox VM (Debian 12), sized and configured per `docs/infrastructure-setup-plan.md`. Docker and Docker Compose are the only host dependencies. Backups are handled at the VM level via Proxmox Backup Server, plus application-level `pg_dump`s per the infra plan.
