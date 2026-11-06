// Minimal service worker: caches the app shell so it installs as an app on phones/desktops.
const CACHE = 'naturalvoice-v6';
const SHELL = [
  '/',
  'app.css',
  'manifest.webmanifest',
  'icon.svg',
  'icon-192.png',
  'icon-512.png',
  'apple-touch-icon.png',
  'favicon-32.png',
];
self.addEventListener(
  'install',
  /** @param {ExtendableEvent} e */ (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))),
);
self.addEventListener(
  'activate',
  /** @param {ExtendableEvent} e */ (e) =>
    e.waitUntil(
      caches
        .keys()
        .then((ks) =>
          Promise.all(ks.filter((k) => k.startsWith('naturalvoice-') && k !== CACHE).map((k) => caches.delete(k))),
        ),
    ),
);
self.addEventListener(
  'fetch',
  /** @param {FetchEvent} e */ (e) => {
    const url = new URL(e.request.url);
    if (e.request.method !== 'GET' || url.pathname.includes('/api/')) return; // never cache audio jobs
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
  },
);
