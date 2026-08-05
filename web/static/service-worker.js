const CACHE_NAME = "rosetta-shell-v7";
const SHELL = [
  "/",
  "/static/css/style.css",
  "/static/css/auth.css",
  "/static/css/skiper-links.css",
  "/static/js/app.js",
  "/static/js/auth.js",
  "/static/js/companion.js",
  "/static/rosetta-icon.svg",
  "/static/rosetta-icon-192.png",
  "/static/rosetta-icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
