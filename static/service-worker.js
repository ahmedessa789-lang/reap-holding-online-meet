const CACHE_NAME = "reap-holding-meet-real-v2-users";
const ASSETS = ["/", "/style.css", "/app.js", "/manifest.json", "/icon.svg"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener("fetch", event => {
  if (event.request.url.includes("/api/") || event.request.url.includes("meet.jit.si")) return;
  event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)));
});