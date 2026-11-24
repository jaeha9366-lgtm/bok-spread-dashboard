/* 주간 동향 분석 — 금리·환율 엑셀 업로드 → GitHub Actions(update_trends.yml)가 보고서 자동 작성.
 * 엑셀은 trend_inputs/weekly/<YYMMDD>.xlsx 로 저장(공개 시장 데이터). 토큰은 위탁운용 업로드와 같은 저장소 키를 공유. */
(function () {
  const REPO = { owner: 'jaeha9366-lgtm', name: 'bok-spread-dashboard', branch: 'main' };
  const API = 'https://api.github.com';
  const TOKEN_ID = 'foiGithubToken';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const css = `
.tu-bg{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;z-index:1000;padding:1rem}
.tu{background:#fff;border-radius:14px;max-width:560px;width:100%;padding:1.3rem 1.4rem;box-shadow:0 20px 50px rgba(0,0,0,.25);max-height:92vh;overflow:auto}
.tu-h{display:flex;justify-content:space-between;align-items:center;font-size:1.05rem;margin-bottom:.4rem}
.tu-x{border:0;background:none;font-size:1.1rem;cursor:pointer;color:#64748b}
.tu-d{color:#475569;font-size:.85rem;line-height:1.7;margin:.2rem 0 .8rem}
.tu-l{display:block;font-weight:600;font-size:.85rem;margin:.8rem 0 .3rem}.tu-l a{font-weight:500}
.tu-hint{color:#94a3b8;font-weight:400}
.tu input[type=file],.tu input[type=password],.tu input[type=date]{width:100%;padding:.5rem;border:1px solid #e2e8f0;border-radius:8px;font-family:inherit}
.tu-c{display:flex;align-items:center;gap:.4rem;font-size:.82rem;color:#475569;margin-top:.4rem}
.tu-go{margin-top:1rem;width:100%;background:#4f46e5;color:#fff;border:0;border-radius:9px;padding:.65rem;font-weight:700;cursor:pointer;font-family:inherit}
.tu-go:disabled{opacity:.5;cursor:default}
.tu-log{margin-top:.8rem;font-size:.82rem;color:#334155;line-height:1.7}
.tu-st{margin-top:.4rem;font-size:.86rem;font-weight:600;color:#1e293b;line-height:1.7}`;

  async function gh(token, path, opts) {
    opts = opts || {};
    const headers = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
    if (token) headers.Authorization = 'Bearer ' + token;
    if (opts.body) headers['Content-Type'] = 'application/json';
    const r = await fetch(API + path, { method: opts.method || 'GET', headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
    if (!r.ok) {
      let msg = '';
      try { msg = (await r.json()).message || ''; } catch (e) { /* 무시 */ }
      const err = new Error(`${r.status} ${msg}`);
      err.status = r.status;
      throw err;
    }
    return r.json();
  }
  const repoPath = (p) => `/repos/${REPO.owner}/${REPO.name}${p}`;

  async function toB64(file) {
    const u8 = new Uint8Array(await file.arrayBuffer());
    let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  }

  async function commitFile(token, path, b64, message, log) {
    log('GitHub에 엑셀 전송 중...');
    const blob = (await gh(token, repoPath('/git/blobs'), { method: 'POST', body: { content: b64, encoding: 'base64' } })).sha;
    for (let attempt = 1; attempt <= 3; attempt++) {
      const ref = await gh(token, repoPath(`/git/ref/heads/${REPO.branch}`));
      const base = await gh(token, repoPath(`/git/commits/${ref.object.sha}`));
      const tree = await gh(token, repoPath('/git/trees'), { method: 'POST', body: {
        base_tree: base.tree.sha, tree: [{ path, mode: '100644', type: 'blob', sha: blob }] } });
      const commit = await gh(token, repoPath('/git/commits'), { method: 'POST', body: { message, tree: tree.sha, parents: [ref.object.sha] } });
      try {
        await gh(token, repoPath(`/git/refs/heads/${REPO.branch}`), { method: 'PATCH', body: { sha: commit.sha, force: false } });
        return commit.sha;
      } catch (e) {
        if (e.status !== 422 || attempt === 3) throw e;
        log('다른 업데이트와 겹쳐 다시 시도합니다...');
      }
    }
  }

  async function watchRun(token, sha, setStatus) {
    const t0 = Date.now();
    let run = null, useToken = true;
    while (Date.now() - t0 < 20 * 60 * 1000) {
      await new Promise((r) => setTimeout(r, run ? 10000 : 6000));
      try {
        const res = await gh(useToken ? token : null, repoPath(`/actions/runs?head_sha=${sha}&per_page=10`));
        run = (res.workflow_runs || []).find((x) => /trend/i.test(x.path || x.name || '')) || null;
      } catch (e) {
        if (useToken && (e.status === 403 || e.status === 401)) { useToken = false; continue; }
        continue;
      }
      if (!run) { setStatus('GitHub Actions 시작 대기 중...'); continue; }
      const link = `<a href="${run.html_url}" target="_blank" rel="noopener">진행 상황 보기</a>`;
      const min = Math.floor((Date.now() - t0) / 60000);
      if (run.status !== 'completed') { setStatus(`⏳ 데이터 검증 → AI 조사·작성 → 한글 파일 생성 중 (${min}분 경과, 보통 3~6분) · ${link}`); continue; }
      if (run.conclusion === 'success') {
        setStatus(`✅ 보고서 작성 완료. 사이트 반영까지 1~2분 걸립니다. 잠시 후 <a href="#" onclick="location.reload();return false;">새로고침</a>해 주세요. · ${link}`);
      } else {
        setStatus(`❌ 보고서 작성 실패 (${run.conclusion}) · ${link} — 로그를 확인해 주세요.`);
      }
      return;
    }
    setStatus('진행 상황 확인 시간이 지났습니다. GitHub Actions 탭에서 확인해 주세요.');
  }

  function lastFriday() {
    const d = new Date();
    const back = (d.getDay() + 2) % 7; // 금요일까지 되돌아갈 일수
    d.setDate(d.getDate() - back);
    return d.toISOString().slice(0, 10);
  }

  function openPanel() {
    let pnl = document.getElementById('tu');
    if (pnl) { pnl.style.display = 'flex'; return; }
    if (!document.getElementById('tu-css')) {
      const st = document.createElement('style'); st.id = 'tu-css'; st.textContent = css; document.head.appendChild(st);
    }
    const saved = localStorage.getItem(TOKEN_ID) || sessionStorage.getItem(TOKEN_ID) || '';
    const wrap = document.createElement('div');
    wrap.innerHTML = `
<div id="tu" class="tu-bg"><div class="tu">
  <div class="tu-h"><b>📤 주간 동향 자료 업로드</b><button type="button" class="tu-x" title="닫기">✕</button></div>
  <p class="tu-d">금리·환율 엑셀을 올리면 GitHub Actions가 <b>공식 데이터와 날짜·값 대조 → AI(Gemini) 뉴스 조사·본문 작성 → 한글(HWPX)·워드 파일 생성 → 이 탭에 게시</b>까지 자동으로 진행합니다(약 3~6분).
  같은 기준일로 다시 올리면 보고서가 새로 작성됩니다.</p>
  <label class="tu-l">엑셀 파일 <span class="tu-hint">— 주간동향_그래프.xlsx (일자 / 환율 / 미국10y / 한국3y)</span></label>
  <input type="file" id="tu-f" accept=".xlsx,.xls">
  <label class="tu-l">기준일 <span class="tu-hint">— 보고서 마지막 날(보통 금요일)</span></label>
  <input type="date" id="tu-d">
  <label class="tu-l">GitHub 토큰 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">(발급)</a>
    <span class="tu-hint">— 이 저장소만, Contents 읽기/쓰기 권한의 Fine-grained 토큰</span></label>
  <input type="password" id="tu-t" placeholder="github_pat_..." autocomplete="off">
  <label class="tu-c"><input type="checkbox" id="tu-keep" ${localStorage.getItem(TOKEN_ID) ? 'checked' : ''}> 이 브라우저에 토큰 저장</label>
  <button type="button" id="tu-go" class="tu-go" disabled>업로드 후 보고서 자동 작성</button>
  <div id="tu-log" class="tu-log"></div>
  <div id="tu-st" class="tu-st"></div>
</div></div>`;
    pnl = wrap.firstElementChild;
    document.body.appendChild(pnl);
    const $ = (id) => document.getElementById(id);
    $('tu-t').value = saved;
    $('tu-d').value = lastFriday();
    const close = () => { pnl.style.display = 'none'; };
    pnl.querySelector('.tu-x').onclick = close;
    pnl.addEventListener('click', (e) => { if (e.target === pnl) close(); });
    const log = (t) => { $('tu-log').insertAdjacentHTML('beforeend', `<div>${t}</div>`); };
    const setStatus = (h) => { $('tu-st').innerHTML = h; };
    const ready = () => { $('tu-go').disabled = !($('tu-f').files.length && $('tu-d').value); };
    $('tu-f').onchange = ready; $('tu-d').onchange = ready;

    $('tu-go').onclick = async () => {
      const token = $('tu-t').value.trim();
      const file = $('tu-f').files[0];
      const base = $('tu-d').value; // YYYY-MM-DD
      $('tu-log').innerHTML = ''; setStatus('');
      if (!token) { log('❌ GitHub 토큰을 입력해 주세요.'); return; }
      try {
        if ($('tu-keep').checked) { localStorage.setItem(TOKEN_ID, token); } else { localStorage.removeItem(TOKEN_ID); sessionStorage.setItem(TOKEN_ID, token); }
      } catch (e) { /* 무시 */ }
      const id = base.slice(2, 4) + base.slice(5, 7) + base.slice(8, 10);
      const ext = /\.xls$/i.test(file.name) ? 'xls' : 'xlsx';
      $('tu-go').disabled = true;
      try {
        const sha = await commitFile(token, `trend_inputs/weekly/${id}.${ext}`, await toB64(file),
          `data: 주간 동향 자료 업로드 (기준일 ${base}, ${file.name.normalize('NFC')})`, log);
        log(`✔ 업로드 완료 (커밋 ${sha.slice(0, 7)}) — 기준일 ${esc(base)}`);
        setStatus('GitHub Actions 시작 대기 중...');
        await watchRun(token, sha, setStatus);
      } catch (e) {
        let hint = '';
        if (e.status === 401) hint = ' — 토큰이 올바르지 않거나 만료되었습니다.';
        else if (e.status === 403 || e.status === 404) hint = ' — 토큰 권한을 확인해 주세요 (이 저장소, Contents: Read and write).';
        log(`❌ 업로드 실패: ${esc(e.message || e)}${hint}`);
      } finally {
        ready();
      }
    };
  }
  window.openTrendUpload = openPanel;
})();
