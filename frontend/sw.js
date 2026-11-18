const CACHE_NAME = "smartspend-pro-v21";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/style.css",
  "/app.js",
  "/auth.js",
  "/finance.js",
  "/tailwind.css",
  "/vendor/chart.umd.min.js",
  "/icons.svg",
  "/favicon.svg",
  "/favicon-32.png",
  "/apple-touch-icon.png",
  "/icons/smartspend-192.png",
  "/icons/smartspend-512.png",
  "/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        }),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/")
  ) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(async (response) => {
        if (
          response.ok &&
          response.headers.get("X-SmartSpend-App") === "1" &&
          STATIC_ASSETS.includes(url.pathname)
        ) {
          const copy = response.clone();
          const canonicalCopy = response.clone();
          event.waitUntil(
            caches.open(CACHE_NAME).then(async (cache) => {
              await cache.put(event.request, copy);
              if (url.search) {
                await cache.put(url.pathname, canonicalCopy);
              }
            }),
          );
        }
        if (
          event.request.mode === "navigate" &&
          (!response.ok || response.headers.get("X-SmartSpend-App") !== "1")
        ) {
          return (await caches.match("/")) || response;
        }
        return response;
      })
      .catch(async () => {
        const exact = await caches.match(event.request);
        if (exact) return exact;
        const ignored = await caches.match(url.pathname, { ignoreSearch: true });
        if (ignored) return ignored;
        if (event.request.mode === "navigate") {
          const home = await caches.match("/");
          if (home) return home;
        }
        return new Response("Ngoại tuyến", { status: 503 });
      }),
  );
});
