# Mobile App

Built as a PWA at `/app/` (the `pwa` Django app). This doc now records what shipped, what's still open, and the original exploration that led here.

## Use cases (as requested, now implemented)

1. Scan a part's barcode → see what it is, current stock quantity, and **where** it is (site/warehouse/bin). ✅ Camera scan via `BarcodeDetector`, with a manual code-entry fallback.
2. Book that part out of stock **onto a specific ticket** (work order) via the scan — decrements stock, records usage. ✅
3. View and open assigned tickets from the phone — update status, log parts against it. ✅
4. Scan an asset's own tag/QR code → land on that asset's history (tickets, configuration, permits/incidents, change log). ✅ Same Scan tab, a part/asset mode toggle; a match hands off to the existing `reporting.views.asset_history_view` page rather than a second asset-detail screen.

## What's built

- **`pwa` app**: `/app/` (the installable shell, `@login_required` — goes through the same Entra OIDC flow as the rest of the internal site, no separate technician login), `/app/sw.js` (service worker, served from `/app/` specifically so its scope covers the whole app rather than just `/static/pwa/`), `/static/pwa/manifest.json` + PNG icons for "add to home screen" on both Android and iOS.
- **No frontend framework, no build step**: a single hand-written `app.js` (vanilla JS, `fetch()`-based) — consistent with this project having no npm/webpack toolchain anywhere else. Reasonable at this size; revisit if the client grows much further.
- **Auth**: session-based, not the `TokenAuthentication` originally anticipated for this — since the PWA runs in the same browser as the rest of the internally-authenticated site, it just rides the existing Entra-authenticated Django session (`SessionAuthentication`, already in `DEFAULT_AUTHENTICATION_CLASSES`) plus a CSRF token read from the cookie and sent as `X-CSRFToken` on writes. `TokenAuthentication` stays in place for any future client that isn't a same-origin browser session (a native app, a script).
- **Backend API it consumes** (`mobile_api`): barcode/SKU lookup with stock+location, "my work orders", ticket detail, status update, consume-part, and (added later, CMMS audit item #3) asset-tag lookup for the asset-scan mode.

**Verified end-to-end**, not just written: real HTTP requests through the actual pages a browser would load — the unauthenticated redirect to Entra, all static assets and the service worker serving with correct content-type/scope, the authenticated shell rendering with a live CSRF cookie, and the full scan → lookup → book workflow (including CSRF actually being enforced — confirmed a request without the header gets a real 403, not silently accepted). Not tested: an actual phone's camera and `BarcodeDetector` in a real browser - the sandbox this was built in has no camera/browser to test against, so the manual code-entry fallback path is what got verified for the "detected a code" half of the flow; the camera-acquisition half is standard `getUserMedia`/`BarcodeDetector` code but hasn't been run against real hardware yet.

## Known gaps, not solved by this pass

- **Offline**: still not implemented. The service worker caches the app shell (so the UI loads offline) but every API call goes straight to the network and fails visibly if there's no connection — no local queue/sync for a scan performed in a dead zone. This was flagged as a real requirement before building started and remains the biggest gap between what shipped and a fully field-ready tool.
- **Camera reliability on real devices, especially iOS Safari**: flagged as a risk before building, not yet resolved by real-device testing. If `BarcodeDetector` proves unreliable in practice, the manual-entry fallback already in place is the safety net, and a JS decoder library (e.g. ZXing) or a native wrapper (Capacitor) are the next steps if that's not good enough.
- **`consume_stock` still only checks physical `quantity_on_hand`**, not whether a walk-up scan eats another ticket's `StockReservation` — unchanged from before, still low risk at small scale.

## Open questions

- Device model: BYOD or company-issued? Matters more now for MDM-based PWA installation/updates than it did pre-build.
- Barcode symbology/label format for spare parts — still needs deciding before printing/relabeling stock.
- Push notifications for new ticket assignment — not implemented (limited/inconsistent on iOS PWAs); "check the list" is the current experience.
- Whether to extend this to PM checklists or photos/signatures for field service — the app shell (tab navigation, `api()` helper) is built generically enough to add screens, but nothing beyond parts/tickets exists yet.

## Original build-approach analysis (for reference)

PWA was chosen over native (React Native/Flutter) for: no app-store distribution needed for an internal tool, reuse of the same server-rendered/no-build-tooling approach as the rest of this project, and because the core use cases didn't inherently need native performance. The tradeoff accepted going in was exactly the two gaps above (offline, camera reliability) — both were known risks before writing any code, not surprises found after.
