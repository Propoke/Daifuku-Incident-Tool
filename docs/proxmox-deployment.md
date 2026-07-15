# Deploying to a Proxmox VM

A concrete, step-by-step runbook for the deployment shape `docs/infrastructure-setup-plan.md` already decided on: one Proxmox VM running Docker Compose (Traefik + Django/Gunicorn + Postgres + Redis + Celery worker/beat). That doc covers the *why*; this one covers the *how*, plus a smoke-test checklist to actually run once the stack is up — this hasn't been run against a real Proxmox VM yet (this repo was built and verified in a sandbox with no Docker daemon access), so treat the first run of this guide as the real test.

## Prerequisites

Before touching Proxmox:

- **A Cloudflare-managed DNS zone** you can create an internal-resolving hostname in, plus a scoped API token (Zone/DNS/Edit, one zone only) — see `README.md` for the exact steps. TLS depends on this even for internal-only access.
- **An Entra ID (Azure AD) app registration** for OIDC login — tenant ID, client ID, client secret, redirect URI `https://<CMMS_HOSTNAME>/oidc/callback/`.
- Decide `CMMS_HOSTNAME` now (e.g. `cmms.internal.yourcompany.com`) — it's baked into the Cloudflare DNS record, the Entra redirect URI, and `.env`, so settling it before provisioning avoids redoing any of those.

## 1. Provision the VM

Per the infra plan's Standard tier sizing:

- **Debian 12** (bookworm) — matches the infra plan's recommendation and has the most predictable Docker packaging. Ubuntu 22.04/24.04 LTS works identically if that's what your Proxmox templates standardize on; adjust package names below if so.
- **8 vCPU / 16GB RAM / 250GB+ disk**, VM (not LXC — avoids Docker-in-LXC nesting quirks, and a VM backs up cleanly as a single unit via Proxmox Backup Server).
- Attach to whatever internal VLAN/subnet your other internal services use. No public IP, no port-forward — inbound stays internal-only per the infra plan; only outbound HTTPS to Microsoft's Entra endpoints and Let's Encrypt/Cloudflare's ACME API need to be allowed out.
- Static internal IP (DHCP reservation or static config) so the internal DNS record you're about to create doesn't drift.

## 2. Base OS setup

SSH into the new VM, then:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y ca-certificates curl git

# Docker Engine + Compose plugin (official repo, not the distro's older docker.io package)
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# run docker without sudo (log out/in after this, or `newgrp docker`)
sudo usermod -aG docker $USER
```

Verify: `docker compose version` should print v2+.

## 3. Create the internal DNS record

In Cloudflare, add an **A record** for `CMMS_HOSTNAME` pointing at the VM's internal IP, with the Cloudflare proxy (orange cloud) turned **off** — this needs to resolve to the VM directly on your internal network, not proxy through Cloudflare's edge. DNS-01 (used for the cert challenge) doesn't require the record to be internet-reachable, only that it exists.

## 4. Clone the repo and configure `.env`

```bash
git clone <this repo's URL> /opt/cmms
cd /opt/cmms
cp .env.example .env
```

Edit `.env` and fill in every value — `README.md`'s "Running the full stack" section has the detailed rationale for each one (Cloudflare token scoping, staging-vs-production ACME endpoint, etc.). At minimum, replace every `changeme`/`your-*`/`*.yourcompany.com` placeholder:

- `DJANGO_SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`
- `POSTGRES_PASSWORD` — a real secret, not the dev default
- `CMMS_HOSTNAME` — the hostname from step 3
- `ACME_EMAIL`, `CF_DNS_API_TOKEN` — from the Cloudflare setup in "Prerequisites"
- `OIDC_TENANT_ID`, `OIDC_RP_CLIENT_ID`, `OIDC_RP_CLIENT_SECRET` — from the Entra app registration
- `DJANGO_ALLOWED_HOSTS` — should include `CMMS_HOSTNAME`
- Set `ACME_CA_SERVER` to the **staging** Let's Encrypt endpoint for the first boot (`https://acme-staging-v02.api.letsencrypt.org/directory`, noted in a comment above the setting in `.env.example`) to avoid burning production rate limits while you're still shaking out the deploy — switch to the production endpoint once a staging cert issues cleanly, then `docker compose up -d` again to reissue for real.
- `DJANGO_EMAIL_BACKEND`/`EMAIL_*` — leave the console backend for the first deploy (emails get logged, not sent) until a real SMTP relay is confirmed; flip to the SMTP backend once that's ready.

## 5. First boot

```bash
docker compose up -d --build
docker compose logs -f backend   # watch collectstatic -> migrate -> gunicorn start
```

The `backend` image's startup command runs `collectstatic`, then `migrate --noinput`, then starts Gunicorn — all data migrations (RBAC groups/permissions, seeded Celery beat schedules for PM generation and the daily notification digest) run automatically as part of `migrate`, so there's no separate seed step. First boot will take longer than restarts since it's also building images and Traefik is requesting the initial cert.

Create the first superuser (needed since a fresh DB has zero users, and role-group permissions alone can't get you into `/admin/` for the very first login):

```bash
docker compose exec backend python manage.py createsuperuser
```

## 6. Smoke test checklist

Run through all of these before calling the deploy done — this is the first time this exact stack has run outside a sandbox with no Docker access, so don't assume anything works until it's actually clicked through:

- [ ] `curl https://<CMMS_HOSTNAME>/healthz` → `{"status": "ok"}` with a real cert (no `-k` needed) — confirms Traefik, the cert, and the backend container are all up.
- [ ] `https://<CMMS_HOSTNAME>/admin/` — log in as the superuser. **Check that the page is actually styled** (this is the WhiteNoise static-file fix — an unstyled admin means static serving broke).
- [ ] `https://<CMMS_HOSTNAME>/` — redirects into the Entra OIDC login flow if not authenticated; completes and lands back in the app for a real internal user.
- [ ] In `/admin/`, create a `Site`, `Terminal`, and `Asset`, then a `WorkOrder` against it. Confirms the core data model and migrations are sound end-to-end, not just that the container started.
- [ ] Upload a file to that `WorkOrder` via the Attachments inline, then open the file's URL directly and confirm it downloads. This is the `/media/` serving fix — a working upload that 404s on download means that regressed.
- [ ] `/admin/django_celery_beat/periodictask/` — confirm "Generate due PM work orders" and "Send daily SLA/stock notification digest" both exist and are enabled (seeded by migrations, not something you create by hand).
- [ ] `docker compose logs celery-worker` and `docker compose logs celery-beat` — both running without crash-looping.
- [ ] `https://<CMMS_HOSTNAME>/app/` — the technician PWA loads, and "Add to Home Screen" is available (needs the real HTTPS cert; confirms both TLS and the PWA's static assets/manifest/service worker are all being served correctly).
- [ ] `https://<CMMS_HOSTNAME>/search/` — search for the asset tag you created above and confirm it comes back.
- [ ] `https://<CMMS_HOSTNAME>/reports/` — dashboard loads without error (exercises most of the ORM/reporting layer at once).
- [ ] Grant a test user's account access to the `Site` created above (`/admin/assets/site/`, `allowed_users`), log in as that user, and confirm they can see the site's data but nothing has ever been created outside their access — this is the site-scoping model the whole RBAC design depends on; worth confirming for real, not just trusting the code.

If `ACME_CA_SERVER` was left on the Let's Encrypt staging endpoint for this run, switch it to production in `.env` and run `docker compose up -d` once more to reissue a trusted cert, then re-check the `curl`/browser steps above without `-k`.

## 7. Ongoing operations

- **Redeploying after a code change**: `git pull && docker compose up -d --build`. Migrations run automatically on the `backend` container's startup, same as first boot.
- **Backups**: Proxmox Backup Server handles VM-level snapshots per the infra plan. In addition, take an application-level `pg_dump` regularly:
  ```bash
  docker compose exec postgres pg_dump -U cmms cmms | gzip > /opt/cmms-backups/cmms-$(date +%F).sql.gz
  ```
  Point this at a location PBS also captures (or a separate target entirely, so backups don't live solely on the VM they're backing up), and actually test a restore once — an untested backup is not a backup.
- **Logs**: `docker compose logs -f <service>` per service (`backend`, `celery-worker`, `celery-beat`, `traefik`, `postgres`, `redis`).
- **Cert renewal**: fully automatic via Traefik's ACME DNS-01 flow — no action needed unless the Cloudflare token expires or is revoked.
