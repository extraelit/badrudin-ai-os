/* Service worker Badrudin AI OS (PR-10) — минимальный кэш оболочки + offline-fallback.
 * Стратегия: network-first для навигации (свежий контент, офлайн-запас), cache-first
 * для статики. НЕ кэширует API-ответы (/… с данными и токенами) — только оболочку. */
const CACHE = "badrudin-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  // Не вмешиваемся в кросс-оригин и в вызовы API (по заголовку Authorization/типу).
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    // Навигация: сеть, при офлайне — кэш оболочки.
    event.respondWith(
      fetch(request).catch(() => caches.match(request).then((r) => r || caches.match("/"))),
    );
    return;
  }
  // Статика: cache-first с дозаписью.
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((resp) => {
          const copy = resp.clone();
          if (resp.ok) caches.open(CACHE).then((c) => c.put(request, copy));
          return resp;
        }).catch(() => cached),
    ),
  );
});
