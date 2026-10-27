/* Acervo da Turma — service worker (deixa o site instalável como aplicativo, abrir rápido e funcionar sem internet).
   - A página (index.html): sempre tenta a versão nova na internet; sem internet (ou se a rede não responde em 6 s),
     abre a última guardada.
   - Ícones, capas e bibliotecas fixas (pdf.js, Tesseract... com a versão no endereço): guardados depois da primeira vez.
   - Figuras do acervo (Supabase Storage, bucket "paginas"): o nome do arquivo é a impressão digital da imagem, então ela
     nunca muda. Guardadas sem o código de acesso do endereço: primeiro as dos temas baixados ("acervo-off-img", que o
     app preenche), depois as já vistas ("acervo-img", até 1500). Além de funcionar sem internet, a mesma figura não é
     baixada de novo do Supabase.
   - Dados, login e IA do Supabase: não passam por aqui (o app guarda a cópia dos dados no IndexedDB). */
const VERSAO = 'acervo-v3';   // v3: capas novas em alta resolução (a v2 guardava as antigas)
const IMG = 'acervo-img', IMG_OFF = 'acervo-off-img', MAX_IMG = 1500;
const FIXOS = /^https:\/\/(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|fastly\.jsdelivr\.net|unpkg\.com|fonts\.gstatic\.com|fonts\.googleapis\.com)\//;
const FIGURA = /\.supabase\.co$/;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSAO).then(c => c.addAll(['/', '/manifest.webmanifest', '/icones/icone-192.png'])).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  // só troca o cache da página e dos fixos; as figuras guardadas continuam
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => /^acervo-v\d+$/.test(k) && k !== VERSAO).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
let guardadas = 0;
async function aparar() {
  const c = await caches.open(IMG); const ks = await c.keys();
  for (const k of ks.slice(0, Math.max(0, ks.length - MAX_IMG))) await c.delete(k);
}
async function figura(req, url) {
  const chave = url.origin + url.pathname;
  const hit = (await caches.match(chave, { cacheName: IMG_OFF })) || (await caches.match(chave, { cacheName: IMG }));
  if (hit) return hit;
  try {
    const r = await fetch(url.href, { mode: 'cors', credentials: 'omit' });
    if (r.ok) { const c = await caches.open(IMG); await c.put(chave, r.clone()); if (++guardadas % 50 === 0) aparar().catch(() => {}); }
    return r;
  } catch (e) { return fetch(req); }
}
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate') {                       // a página: internet primeiro
    e.respondWith((async () => {
      const guardada = caches.match('/', { cacheName: VERSAO });
      const rede = fetch(req).then(r => { if (r.ok && !url.search.includes('aquecer')) { const c = r.clone(); caches.open(VERSAO).then(x => x.put('/', c)); } return r; });
      // rede lenta (Wi-Fi sem internet): depois de 6 s abre a guardada; a nova fica para a próxima vez
      const prazo = new Promise(res => setTimeout(res, 6000)).then(() => guardada);
      try { const r = await Promise.race([rede, prazo]); if (r) return r; return await rede; }
      catch { return (await guardada) || Response.error(); }
    })());
    return;
  }
  if (FIGURA.test(url.hostname) && url.pathname.startsWith('/storage/v1/object/sign/paginas/')) { e.respondWith(figura(req, url)); return; }
  const local = url.origin === self.location.origin && /^\/(icones\/|capas\/|manifest\.webmanifest$)/.test(url.pathname);
  if (local || FIXOS.test(req.url)) {                   // fixos: guardados
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(r => {
      if (r.ok || r.type === 'opaque') { const c = r.clone(); caches.open(VERSAO).then(x => x.put(req, c)); }
      return r;
    })));
  }
});
