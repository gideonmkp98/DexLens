// DexLens Service Worker — Phase 8 Production Readiness
const CACHE_NAME = "dexlens-v1-static";
const STATIC_ASSETS = [
  "/",
  "/offline",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(STATIC_ASSETS).catch(() => {
          // Non-fatal if specific pre-cache asset fails
        });
      })
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => {
        return Promise.all(
          keys
            .filter((key) => key !== CACHE_NAME)
            .map((key) => caches.delete(key))
        );
      })
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // 1. Never intercept non-GET requests
  if (event.request.method !== "GET") {
    return;
  }

  // 2. NEVER cache API requests, scan uploads, or authenticated endpoints
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/uploads/") ||
    url.protocol.startsWith("chrome-extension")
  ) {
    return;
  }

  // 3. For Next.js static bundles and public images: Cache-first with network refresh
  if (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.match(/\.(png|svg|webp|ico|woff2)$/)
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const networkFetch = fetch(event.request)
          .then((response) => {
            if (response && response.status === 200) {
              const clone = response.clone();
              caches
                .open(CACHE_NAME)
                .then((cache) => cache.put(event.request, clone));
            }
            return response;
          })
          .catch(() => cached);

        return cached || networkFetch;
      })
    );
    return;
  }

  // 4. For page navigations: Network-first, fallback to /offline on total network failure
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        const offlinePage = await caches.match("/offline");
        if (offlinePage) return offlinePage;
        return new Response(
          '<!DOCTYPE html><html><body style="background:#20251f;color:#f3efdf;font-family:sans-serif;padding:2rem;text-align:center;"><h2>DexLens is offline</h2><p>Controleer je internetverbinding om kaarten te scannen.</p></body></html>',
          { headers: { "Content-Type": "text/html" } }
        );
      })
    );
  }
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
