const CACHE_VERSION = "agent-bazaar-v1";
const SHELL = [
  "/offline",
  "/static/offline.html",
  "/static/offline.css",
  "/static/offline.js",
  "/static/styles.css",
  "/static/premium.css",
  "/static/platform.css",
  "/static/app.js",
  "/static/platform.js",
  "/manifest.webmanifest",
  "/static/pwa/icon-192.png",
  "/static/pwa/icon-512.png",
  "/static/pwa/maskable-192.png",
  "/static/pwa/maskable-512.png",
  "/static/pwa/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) =>
      Promise.allSettled(SHELL.map((url) => cache.add(url)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  try {
    const response = await fetch(request);
    if (response && response.ok) cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return cache.match("/offline");
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  const cached = await cache.match(request);
  if (cached) {
    fetch(request)
      .then((response) => {
        if (response && response.ok) cache.put(request, response.clone());
      })
      .catch(() => {});
    return cached;
  }
  const response = await fetch(request);
  if (response && response.ok) cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request));
    return;
  }
  if (url.pathname.startsWith("/static/") || url.pathname === "/manifest.webmanifest") {
    event.respondWith(cacheFirst(request));
  }
});
