const CACHE_NAME = "cmms-pwa-v1";
const APP_SHELL = [
  "/app/",
  "/static/pwa/app.js",
  "/static/pwa/style.css",
  "/static/pwa/manifest.json",
  "/static/pwa/icon-192.png",
  "/static/pwa/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls always hit the network - no offline action queue yet (see
  // docs/mobile-app-backlog.md). Let them fail visibly if offline rather
  // than serving stale/cached data for a scan-and-book workflow.
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
});
