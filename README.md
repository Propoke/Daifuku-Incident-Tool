# Daifuku Incident Tool — CMMS

Custom, self-hosted CMMS for maintaining material handling/automation equipment, blending GLPI (asset/config management, ticketing) and ServiceMax (field service, entitlements) concepts. See:

- [`docs/cmms-feature-draft.md`](docs/cmms-feature-draft.md) — feature list, high-level description, and the architectural risk audit.
- [`docs/infrastructure-setup-plan.md`](docs/infrastructure-setup-plan.md) — tech stack, deployment topology, networking, auth, and backup strategy.

This repo currently contains the **walking skeleton**: Traefik + PostgreSQL + an empty Django project with Entra ID (OIDC) login wired up. It exists to validate the deployment shape and auth flow before the real Asset/Configuration data model is built on top of it.

## Stack

Django + Django REST Framework, PostgreSQL, Traefik (TLS termination), Entra ID via `mozilla-django-oidc`. Full rationale in the infra plan doc above.

## Running locally

1. Copy the env template and fill in real values:
   ```
   cp .env.example .env
   ```
   - `DJANGO_SECRET_KEY`: generate one, e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - `POSTGRES_PASSWORD`: any local dev value
   - `OIDC_TENANT_ID` / `OIDC_RP_CLIENT_ID` / `OIDC_RP_CLIENT_SECRET`: from an Entra ID app registration (redirect URI `https://<CMMS_HOSTNAME>/oidc/callback/`). Login won't work without these, but the rest of the stack (health check, admin) runs fine without them.

2. Generate a self-signed cert for local/internal TLS:
   ```
   ./certs/generate-self-signed.sh cmms.internal.local
   ```
   Point `CMMS_HOSTNAME` in `.env` at the same domain, and add it to your hosts file if testing locally (e.g. `127.0.0.1 cmms.internal.local`).

3. Build and start the stack:
   ```
   docker compose up -d --build
   ```

4. Verify:
   - `curl -k https://cmms.internal.local/healthz` → `{"status": "ok"}`
   - `https://cmms.internal.local/admin/` — Django admin (create a superuser first: `docker compose exec backend python manage.py createsuperuser`)
   - `https://cmms.internal.local/` — redirects to Entra ID login if not authenticated (requires real OIDC app registration values in `.env`)

## Deploying

Target environment: a single Proxmox VM (Debian 12), sized and configured per `docs/infrastructure-setup-plan.md`. Docker and Docker Compose are the only host dependencies. Backups are handled at the VM level via Proxmox Backup Server, plus application-level `pg_dump`s per the infra plan.
