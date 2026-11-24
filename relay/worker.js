/* 주간 동향 자료 업로드 중계 서버 (Cloudflare Worker)
 * 대시보드(로그인 없음) → 이 Worker(업로드 비밀번호 확인) → GitHub 저장소에 엑셀 커밋 → Actions 자동 작성
 * Secrets (wrangler secret put):
 *   GH_TOKEN         이 저장소만 허용한 Fine-grained 토큰 (Contents: Read and write, Actions: Read)
 *   UPLOAD_PASSWORD  대시보드 업로드 비밀번호
 */
const OWNER = 'jaeha9366-lgtm', REPO = 'bok-spread-dashboard', BRANCH = 'main', WF = 'update_trends.yml';
const ORIGINS = ['https://jaeha9366-lgtm.github.io', 'null', 'http://localhost:8000', 'http://127.0.0.1:8000'];
const MAX_B64 = 8 * 1024 * 1024; // 약 6MB 파일

function corsHeaders(req) {
  const o = req.headers.get('Origin') || '';
  return {
    'Access-Control-Allow-Origin': ORIGINS.includes(o) ? o : ORIGINS[0],
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

async function gh(env, path, opts = {}) {
  const r = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}${path}`, {
    method: opts.method || 'GET',
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'foi-trend-relay',
      ...(opts.body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return r;
}

async function sameSecret(a, b) {
  const enc = new TextEncoder();
  const [x, y] = await Promise.all([crypto.subtle.digest('SHA-256', enc.encode(a)), crypto.subtle.digest('SHA-256', enc.encode(b))]);
  const u = new Uint8Array(x), v = new Uint8Array(y);
  let d = 0;
  for (let i = 0; i < u.length; i++) d |= u[i] ^ v[i];
  return d === 0;
}

export default {
  async fetch(req, env) {
    const h = corsHeaders(req);
    const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { ...h, 'Content-Type': 'application/json; charset=utf-8' } });
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: h });
    const url = new URL(req.url);
    try {
      if (!env.GH_TOKEN || !env.UPLOAD_PASSWORD) return json({ error: '중계 서버 설정(GH_TOKEN/UPLOAD_PASSWORD)이 비어 있습니다.' }, 500);

      if (url.pathname === '/upload' && req.method === 'POST') {
        const b = await req.json();
        if (!(await sameSecret(String(b.password || ''), env.UPLOAD_PASSWORD))) {
          await new Promise((r) => setTimeout(r, 800));
          return json({ error: '업로드 비밀번호가 올바르지 않습니다.' }, 401);
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(b.base || '')) return json({ error: '기준일 형식이 올바르지 않습니다.' }, 400);
        if (!b.b64 || typeof b.b64 !== 'string' || b.b64.length > MAX_B64) return json({ error: '파일이 없거나 너무 큽니다(6MB 이하).' }, 400);
        const name = String(b.filename || 'data.xlsx').slice(0, 120);
        const ext = /\.xls$/i.test(name) ? 'xls' : 'xlsx';
        const id = b.base.slice(2, 4) + b.base.slice(5, 7) + b.base.slice(8, 10);
        const path = `trend_inputs/weekly/${id}.${ext}`;
        let sha;
        const cur = await gh(env, `/contents/${path}?ref=${BRANCH}`);
        if (cur.ok) sha = (await cur.json()).sha;
        const put = await gh(env, `/contents/${path}`, {
          method: 'PUT',
          body: { message: `data: 주간 동향 자료 업로드 (기준일 ${b.base}, ${name})`, content: b.b64, branch: BRANCH, ...(sha ? { sha } : {}) },
        });
        const res = await put.json();
        if (!put.ok) return json({ error: `GitHub 저장 실패 (${put.status}) ${res.message || ''}` }, 502);
        return json({ ok: true, commit: res.commit && res.commit.sha, path });
      }

      if (url.pathname === '/status') {
        const sha = url.searchParams.get('sha') || '';
        const q = /^[0-9a-f]{7,40}$/.test(sha) ? `?head_sha=${sha}&per_page=1` : '?per_page=1';
        const r = await gh(env, `/actions/workflows/${WF}/runs${q}`);
        const d = await r.json();
        if (!r.ok) return json({ error: `진행 상황 조회 실패 (${r.status}) ${d.message || ''}` }, 502);
        const run = (d.workflow_runs || [])[0];
        return json({ run: run ? { status: run.status, conclusion: run.conclusion, url: run.html_url, created: run.created_at } : null });
      }

      return json({ ok: true, service: 'foi trend relay' });
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};
