# Daifuku Incident Tool — CMMS

Custom, self-hosted CMMS for maintaining material handling/automation equipment, blending GLPI (asset/config management, ticketing) and ServiceMax (field service, entitlements) concepts. See:

- [`docs/cmms-feature-draft.md`](docs/cmms-feature-draft.md) — feature list, high-level description, and the architectural risk audit.
- [`docs/infrastructure-setup-plan.md`](docs/infrastructure-setup-plan.md) — tech stack, deployment topology, networking, auth, and backup strategy.
- [`docs/mobile-app-backlog.md`](docs/mobile-app-backlog.md) — not built yet: plan for a technician phone app (barcode scan → stock/location lookup, book a part onto a ticket, work tickets from the phone), and the API it'll consume.

Started as a **walking skeleton** (Traefik + PostgreSQL + Django with Entra ID login) to validate the deployment shape and auth flow before building on top of it. Now also includes: the Asset/Configuration data model (`assets`), Work Orders/incidents (`workorders`), RBAC roles + site-scoped data access (`core`, `assets/access.py`), teams and shifts (`teams`), PM scheduling with Celery-driven auto-ticketing (`maintenance`), stock/reservation tracking (`inventory`), a token-authenticated API for the future mobile app (`mobile_api`), an MTTR/PM-compliance/SLA/cost dashboard (`reporting`), SLA measurement against service contracts (`workorders/sla.py`), and permit-to-work/incident reporting (`safety`).

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

## PM scheduling

`celery-worker` and `celery-beat` (see `docker-compose.yml`) turn due `PMSchedule`s into `WorkOrder`s automatically, on the cadence set in `/admin/django_celery_beat/periodictask/` (daily by default — editable there, no redeploy needed). To run it manually instead of waiting for the schedule: `python manage.py generate_due_pm_work_orders` (works with just Postgres, no Celery/Redis required for this manual path).

## Deploying

Target environment: a single Proxmox VM (Debian 12), sized and configured per `docs/infrastructure-setup-plan.md`. Docker and Docker Compose are the only host dependencies. Backups are handled at the VM level via Proxmox Backup Server, plus application-level `pg_dump`s per the infra plan.
