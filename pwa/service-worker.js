// Service worker v4 — KILL SWITCH : vide ses propres caches et force le reload des clients.
// Aucune intervention manuelle sur le navigateur n'est requise.
const CACHE = "quinte-v4";

self.addEventListener("install", e => {
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    // 1. Vide TOUS les caches gérés par ce service worker (pas le cache navigateur global)
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      // 2. Prend le contrôle des onglets ouverts
      .then(() => self.clients.claim())
      // 3. Force chaque onglet/PWA à se recharger pour récupérer la nouvelle version
      .then(() => self.clients.matchAll({type: "window"}))
      .then(clients => clients.forEach(c => c.navigate(c.url)))
  );
});

// Réseau d'abord pour les pages et JSON (toujours frais), cache uniquement en fallback
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request)
      .then(r => {
        const clone = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone)).catch(() => {});
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});
