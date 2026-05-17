const CACHE_NAME = "reverie-pwa-v58";
const PAGE_CACHE_NAME = "reverie-pages-v58";
const STATIC_ASSETS = [
  "/",
  "/search",
  "/entities",
  "/uploads",
  "/account",
  "/profile",
  "/privacy",
  "/account-deletion",
  "/tasks",
  "/static/manifest.json",
  "/static/reverie-home.css",
  "/static/reverie-website.css",
  "/static/reverie-home.js",
  "/static/reverie-list-page.css",
  "/static/reverie-list-page.js",
  "/static/reverie-search.min.js",
  "/static/reverie-entities.min.js",
  "/static/reverie-uploads.min.js",
  "/static/reverie-capture.js",
  "/static/reverie-shared.js",
  "/static/reverie-notifications.min.js",
  "/static/reverie-account.js",
  "/static/onboarding/home.png",
  "/static/onboarding/capture-plus.jpg",
  "/static/onboarding/search.png",
  "/static/onboarding/tasks.png",
  "/static/onboarding/account.png",
  "/static/logo_reverie.webp",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => ![CACHE_NAME, PAGE_CACHE_NAME].includes(key)).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (request.headers.get("X-Reverie-App-Shell") === "1") {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      caches.open(PAGE_CACHE_NAME).then((cache) =>
        fetch(request)
          .then((response) => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          })
          .catch(() => cache.match(request).then((cached) => cached || caches.match("/") || Response.error()))
      )
    );
    return;
  }

  if (url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) {
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
