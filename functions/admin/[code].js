const ADMIN_CODE = 'X8Ya_pVX-9RMVPmRPAZZgypBu-Gm8faPeFFmdavFLtV3_';
const CORS = { 'Access-Control-Allow-Origin': '*' };

export async function onRequest(context) {
  const { params, request, env } = context;
  if (request.method !== 'GET') return new Response('Method Not Allowed', { status: 405, headers: CORS });
  if (params.code !== ADMIN_CODE) return new Response('Forbidden', { status: 403, headers: CORS });

  let logs = [];
  if (env && env.VISITS) {
    try { logs = (await env.VISITS.get('logs', { type: 'json' })) || []; } catch (e) {}
  }
  return new Response(JSON.stringify(logs), {
    headers: Object.assign({}, CORS, { 'Content-Type': 'application/json' }),
  });
}
