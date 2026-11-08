const CACHE_NAME = "smartspend-pro-v5";
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
  "/manifest.json"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
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
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Với các API call (/api/...), luôn gọi trực tiếp tới server để lấy dữ liệu thời gian thực từ Supabase
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return;
  }

  event.respondWith(
    fetch(event.request).then(async (response) => {
      if (response.ok && response.headers.get("X-SmartSpend-App") === "1" && STATIC_ASSETS.includes(url.pathname)) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy)));
      }
      if (event.request.mode === "navigate" && (!response.ok || response.headers.get("X-SmartSpend-App") !== "1")) {
        return (await caches.match("/")) || response;
      }
      return response;
    }).catch(async () => (await caches.match(event.request)) || new Response("Ngoại tuyến", { status: 503 }))
  );
});

