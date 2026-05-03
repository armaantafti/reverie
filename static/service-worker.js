const CACHE_NAME = "reverie-pwa-v32";
const PAGE_CACHE_NAME = "reverie-pages-v32";
const STATIC_ASSETS = [
  "/",
  "/search",
  "/entities",
  "/uploads",
  "/privacy",
  "/tasks",
  "/recommendations",
  "/static/manifest.json",
  "/static/reverie-home.min.css",
  "/static/reverie-home.min.js",
  "/static/reverie-list-page.min.css",
  "/static/reverie-list-page.min.js",
  "/static/reverie-search.min.js",
  "/static/reverie-entities.min.js",
  "/static/reverie-uploads.min.js",
  "/static/reverie-capture.min.js",
  "/static/reverie-shared.min.js",
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
        cache.match(request).then((cached) => {
          const network = fetch(request)
            .then((response) => {
              if (response.ok) cache.put(request, response.clone());
              return response;
            })
            .catch(() => cached || caches.match("/") || Response.error());
          return cached || network;
        })
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
