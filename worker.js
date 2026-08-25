// Cloudflare Worker (classic format): CORS-прокси к OpenCode Zen + опционально лог посетителей для админки.
// KV/VISITS и ADMIN_CODE — опциональны (для админки позже). Без них работает только прокси.

// Код доступа к админке (совпадает с тем, что знает владелец).
const ADMIN_CODE = 'X8Ya_pVX-9RMVPmRPAZZgypBu-Gm8faPeFFmdavFLtV3_';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': '*',
};

async function logVisit(req) {
  if (typeof VISITS === 'undefined') return;
  try {
    const ip = req.headers.get('cf-connecting-ip') || '';
    const country = req.headers.get('cf-ipcountry') || '';
    const asn = req.headers.get('cf-asn') || '';
    const ua = req.headers.get('user-agent') || '';
    const ref = req.headers.get('referer') || '';
    const now = new Date().toISOString();
    let logs = await VISITS.get('logs', { type: 'json' }) || [];
    logs.push({ time: now, ip, country, asn, ua, ref });
    if (logs.length > 500) logs.splice(0, logs.length - 500);
    await VISITS.put('logs', JSON.stringify(logs));
  } catch (e) { /* best-effort */ }
}

async function handle(req, event) {
  const url = new URL(req.url);

  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS });
  }

  // Админка: список посетителей по коду ( ?code= или /admin/{code} )
  if (req.method === 'GET' && (url.pathname === '/admin' || url.pathname.startsWith('/admin/'))) {
    let code = url.searchParams.get('code');
    if (url.pathname.startsWith('/admin/')) code = decodeURIComponent(url.pathname.slice('/admin/'.length));
    if (typeof ADMIN_CODE === 'undefined' || code !== ADMIN_CODE) {
      return new Response('Forbidden', { status: 403, headers: CORS });
    }
    const logs = (typeof VISITS !== 'undefined') ? (await VISITS.get('logs', { type: 'json' }) || []) : [];
    return new Response(JSON.stringify(logs), {
      headers: Object.assign({}, CORS, { 'Content-Type': 'application/json' }),
    });
  }

  if (req.method === 'POST' && url.pathname.startsWith('/zen/') && typeof VISITS !== 'undefined') {
    event.waitUntil(logVisit(req));
  }

  const target = 'https://opencode.ai' + url.pathname + url.search;
  let up;
  try {
    up = await fetch(target, {
      method: req.method,
      headers: req.headers,
      body: req.body,
      redirect: 'follow',
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: 'upstream_unreachable', detail: String(e) }), {
      status: 502,
      headers: Object.assign({}, CORS, { 'Content-Type': 'application/json' }),
    });
  }
  const resp = new Response(up.body, up);
  resp.headers.set('Access-Control-Allow-Origin', '*');
  return resp;
}

addEventListener('fetch', event => {
  event.respondWith(handle(event.request, event));
});
