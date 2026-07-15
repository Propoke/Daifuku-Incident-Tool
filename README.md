# Daifuku Incident Tool — CMMS

Custom, self-hosted CMMS for maintaining material handling/automation equipment, blending GLPI (asset/config management, ticketing) and ServiceMax (field service, entitlements) concepts. See:

- [`docs/cmms-feature-draft.md`](docs/cmms-feature-draft.md) — feature list, high-level description, and the architectural risk audit.
- [`docs/infrastructure-setup-plan.md`](docs/infrastructure-setup-plan.md) — tech stack, deployment topology, networking, auth, and backup strategy.

This repo currently contains the **walking skeleton**: Traefik + PostgreSQL + an empty Django project with Entra ID (OIDC) login wired up. It exists to validate the deployment shape and auth flow before the real Asset/Configuration data model is built on top of it.

## Stack

Django + Django REST Framework, PostgreSQL, Traefik (TLS termination via Let's Encrypt DNS-01 through Cloudflare), Entra ID via `mozilla-django-oidc`. Full rationale in the infra plan doc above, including why a public CA cert on a split-horizon hostname was chosen over a self-signed or internal CA.

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

1. Copy the env template and fill in real values:
   ```
   cp .env.example .env
   ```
   - `DJANGO_SECRET_KEY`: generate one, e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `POSTGRES_PASSWORD`: any value for local/staging, a real secret for production
   - `CMMS_HOSTNAME`: a real hostname in a Cloudflare-managed DNS zone (can resolve internally-only — it doesn't need to be internet-reachable, DNS-01 doesn't require that)
   - `ACME_EMAIL`: a real address Let's Encrypt can send expiry/problem notices to
   - `CF_DNS_API_TOKEN`: a Cloudflare API token scoped to `Zone:DNS:Edit` for that zone specifically — not the global API key
   - `ACME_CA_SERVER`: leave as the production Let's Encrypt endpoint, or point at `https://acme-staging-v02.api.letsencrypt.org/directory` while testing to avoid production rate limits
   - `OIDC_TENANT_ID` / `OIDC_RP_CLIENT_ID` / `OIDC_RP_CLIENT_SECRET`: from an Entra ID app registration (redirect URI `https://<CMMS_HOSTNAME>/oidc/callback/`)

2. Build and start the stack:
   ```
   docker compose up -d --build
   ```
   Traefik requests and renews the cert automatically via Cloudflare's DNS API on first boot — no manual cert handling. `traefik/acme/acme.json` (gitignored — it holds the account key and issued certs) is created with restrictive permissions on first run.

3. Verify:
   - `curl https://<CMMS_HOSTNAME>/healthz` → `{"status": "ok"}` (real cert, no `-k` needed)
   - `https://<CMMS_HOSTNAME>/admin/` — Django admin (create a superuser first: `docker compose exec backend python manage.py createsuperuser`)
   - `https://<CMMS_HOSTNAME>/` — redirects to Entra ID login if not authenticated

## Deploying

Target environment: a single Proxmox VM (Debian 12), sized and configured per `docs/infrastructure-setup-plan.md`. Docker and Docker Compose are the only host dependencies. Backups are handled at the VM level via Proxmox Backup Server, plus application-level `pg_dump`s per the infra plan.
