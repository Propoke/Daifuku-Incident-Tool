# Mobile App — Backlog

Not built yet. This is the exploration + plan for a phone app for warehouse/field technicians, and a record of what's already in place on the backend to support it.

## Use cases (as requested)

1. Scan a part's barcode → see what it is, current stock quantity, and **where** it is (site/warehouse/bin).
2. Book that part out of stock **onto a specific ticket** (work order) via the scan — decrements stock, records usage.
3. View and open assigned tickets from the phone (not just look at them — work them: update status, add the above part usage).

## What's already built (the API contract this app will consume)

To avoid the mobile app build starting from zero, the backend prerequisites are done now, under `api/mobile/` (token-authenticated, `Authorization: Token <key>`):

| Endpoint | Purpose |
|---|---|
| `GET /api/mobile/spareparts/lookup/?code=<value>` | Barcode-or-SKU lookup → part info + stock/location per warehouse |
| `GET /api/mobile/workorders/mine/` | Tickets assigned to the logged-in user |
| `GET /api/mobile/workorders/<id>/` | Ticket detail |
| `POST /api/mobile/workorders/<id>/status/` | Update ticket status from the phone |
| `POST /api/mobile/workorders/<id>/consume-part/` | The barcode "book it out onto this ticket" action |

Backing data model (`inventory` app): `StockLocation` (warehouse/bin within a site), `StockLevel` (quantity on hand per part per location, with reservation-aware `quantity_available`), `StockReservation` (plan ahead without touching on-hand stock). `SparePart` gained a `barcode` field, separate from `sku`, with lookup falling back to SKU if no barcode is scanned/matched.

All of this already went through the same RBAC permission table used everywhere else in the admin (`mobile_api.permissions.HasModelPermission` checks the same `app_label.codename` permissions) — no separate API-only authorization scheme to maintain.

**Verified**, not just written: real HTTP requests against a running server with token auth, including the full scan → consume → stock-decrements → reservation-auto-fulfills path, RBAC blocking a view-only role from the write actions, and the insufficient-stock error path.

## Known gap in what's built

`consume_stock` only checks physical `quantity_on_hand` - it doesn't yet prevent one ticket's walk-up scan from eating stock another ticket has reserved via `StockReservation`. Low risk at small scale, worth revisiting if reservations see real use before the mobile app ships.

## Build approach: PWA vs. native

| | **PWA** (recommended starting point) | **Native (React Native / Flutter)** |
|---|---|---|
| Distribution | Add-to-home-screen, no app store, no MDM needed for an internal tool | App store review (or internal/enterprise distribution via MDM) |
| Barcode scanning | Browser camera + a JS decoder (e.g. ZXing) or the `BarcodeDetector` API where supported | Native camera SDK (e.g. ML Kit) - generally faster/more reliable recognition, better low-light/damaged-label handling |
| Offline | Service worker + IndexedDB - workable but more manual plumbing | Native local storage/SQLite - more mature offline story |
| Push notifications | Limited, especially on iOS | Full support |
| Codebase | Reuses the eventual React web frontend (same components/API client) | Separate codebase and toolchain |
| Effort to first working version | Lower | Higher |

**Recommendation**: start with a PWA. It reuses the web frontend work already planned, avoids app-store distribution overhead for an internal tool, and the core use cases (lookup, view tickets, scan-and-book) don't inherently need native performance. The real risk is barcode-scanning reliability in-browser, particularly on iOS Safari where `BarcodeDetector` support has historically been inconsistent — if that turns out to be a blocker in practice, the fallback is either a JS decoder library (slower but works everywhere) or wrapping the same web app natively (e.g. Capacitor) to get a native camera API without a full rewrite.

## Auth for the mobile client

What's implemented now (DRF `TokenAuthentication`) is an **interim mechanism** to unblock building/testing a client — an admin issues a static token per user (`/admin/authtoken/tokenproxy/` or `manage.py drf_create_token <username>`). For a real rollout, this should move to Entra ID's mobile-native OAuth2 Authorization Code + PKCE flow (system browser / `ASWebAuthenticationSession` on iOS, Chrome Custom Tabs on Android) rather than an embedded webview or long-lived static tokens — same identity provider as the web app, no separate credential to manage per user, and tokens that actually expire/refresh.

## Offline

Warehouse basements and steel-shelving areas are classic dead zones. The scan → consume-part action should be designed to queue locally and sync when connectivity returns, with a visible "pending sync" state — not solved here, but worth stating as a requirement before someone starts building, since it changes the client architecture (can't just be a thin API-calling shell).

## Open questions before building

- Device model: BYOD (technicians' own phones) or company-issued/kiosk devices? Affects the PWA-vs-native calculus and whether MDM is already in play.
- Barcode symbology and label format for spare parts — needs deciding before printing/relabeling stock (Code128 and QR are both reasonable; QR gives more room for encoding SKU+extra metadata if useful later).
- Are push notifications for new ticket assignment actually wanted, or is "check the list" sufficient? Changes the PWA-vs-native tradeoff.
- Should the phone app eventually cover more than parts/tickets (e.g. PM checklists, photos/signatures for field service) — worth knowing before locking in an architecture that only optimizes for the barcode flow.
