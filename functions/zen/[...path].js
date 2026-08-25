const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': '*',
};

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });

  const url = new URL(request.url);
  const target = 'https://opencode.ai' + url.pathname + url.search;

  let up;
  try {
    up = await fetch(target, {
      method: request.method,
      headers: request.headers,
      body: request.body,
      redirect: 'follow',
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: 'upstream_unreachable', detail: String(e) }), {
      status: 502,
      headers: Object.assign({}, CORS, { 'Content-Type': 'application/json' }),
    });
  }

  // лог посетителя (только для обращений к /zen)
  if (request.method === 'POST' && env && env.VISITS) {
    try {
      const ip = request.headers.get('cf-connecting-ip') || '';
      const country = request.headers.get('cf-ipcountry') || '';
      const asn = request.headers.get('cf-asn') || '';
      const ua = request.headers.get('user-agent') || '';
      const ref = request.headers.get('referer') || '';
      const now = new Date().toISOString();
      let logs = (await env.VISITS.get('logs', { type: 'json' })) || [];
      logs.push({ time: now, ip, country, asn, ua, ref });
      if (logs.length > 500) logs.splice(0, logs.length - 500);
      await env.VISITS.put('logs', JSON.stringify(logs));
    } catch (e) { /* best-effort */ }
  }

  const resp = new Response(up.body, up);
  resp.headers.set('Access-Control-Allow-Origin', '*');
  return resp;
}
