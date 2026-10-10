/* Acervo da Turma — service worker (deixa o site instalável como aplicativo e abrir rápido).
   - A página (index.html): sempre tenta a versão nova na internet; sem internet, abre a última guardada.
   - Ícones e bibliotecas fixas (pdf.js, Tesseract... com a versão no endereço): guardados depois da primeira vez.
   - Supabase (dados, login, IA) e tudo o que não é GET: nunca passa por aqui (sempre ao vivo). */
const VERSAO = 'acervo-v1';
const FIXOS = /^https:\/\/(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|fastly\.jsdelivr\.net|unpkg\.com|fonts\.gstatic\.com|fonts\.googleapis\.com)\//;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSAO).then(c => c.addAll(['/', '/manifest.webmanifest', '/icones/icone-192.png'])).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSAO).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate') {                       // a página: internet primeiro
    e.respondWith(fetch(req).then(r => { if (r.ok) { const c = r.clone(); caches.open(VERSAO).then(x => x.put('/', c)); } return r; })
      .catch(() => caches.match('/').then(r => r || Response.error())));
    return;
  }
  const local = url.origin === self.location.origin && /^\/(icones\/|manifest\.webmanifest$)/.test(url.pathname);
  if (local || FIXOS.test(req.url)) {                   // fixos: guardados
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok || r.type === 'opaque') { const c = r.clone(); caches.open(VERSAO).then(x => x.put(req, c)); }
      return r;
    })));
  }
});
