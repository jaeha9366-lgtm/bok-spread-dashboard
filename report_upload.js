/* 위탁운용 자료 업로드: 브라우저에서 엑셀을 보고서 비밀번호로 암호화 → GitHub에 커밋 → Actions가 보고서 재생성.
 * 원본 엑셀은 암호화된 상태로만 전송·저장된다 (report_data_enc/*.enc). 형식·슬롯 규칙은 report_inputs.py 와 동일. */
(function () {
  'use strict';
  const REPO = { owner: 'jaeha9366-lgtm', name: 'bok-spread-dashboard', branch: 'main' };
  const API = 'https://api.github.com';
  const KEY_ID = 'foiReportKey', TOKEN_ID = 'foiGithubToken';
  const MAGIC = new TextEncoder().encode('FOIENC1\n');
  const TYPE_LABEL = { nav: '일자별 기준가', trades: '채권매매 손익', holdings: '보유내역(취합본)' };

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const b64d = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  function toB64(u8) {
    return new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(String(fr.result).split(',')[1]);
      fr.onerror = rej;
      fr.readAsDataURL(new Blob([u8]));
    });
  }
  async function sha8(text) {
    const d = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
    return Array.from(d.slice(0, 4)).map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  // 파일명 → 저장 슬롯 (report_inputs.slot_for 와 동일)
  async function slotFor(name) {
    if (name.includes('기준가')) return { slot: 'nav', label: TYPE_LABEL.nav };
    if (name.includes('매매')) return { slot: 'trades', label: TYPE_LABEL.trades };
    if (name.includes('헤지')) {
      const m = name.match(/\d+년\s*(\S+?)\s*헤지/);
      const mgr = m ? m[1] : name;
      return { slot: 'hedge-' + (await sha8(mgr)), label: `환헤지비율(${mgr})` };
    }
    if (name.includes('취합본')) return { slot: 'holdings', label: TYPE_LABEL.holdings };
    return null;
  }
  function reportKey() {
    try {
      const s = sessionStorage.getItem(KEY_ID);
      if (s) return s;
      const l = JSON.parse(localStorage.getItem(KEY_ID) || 'null');
      if (l && l.exp > Date.now()) return l.k;
    } catch (e) { /* 무시 */ }
    return null;
  }
  async function encryptFile(file, name, keyB64) {
    const key = await crypto.subtle.importKey('raw', b64d(keyB64), 'AES-GCM', false, ['encrypt']);
    const nb = new TextEncoder().encode(name);
    const data = new Uint8Array(await file.arrayBuffer());
    const pt = new Uint8Array(2 + nb.length + data.length);
    pt[0] = nb.length >> 8; pt[1] = nb.length & 255;
    pt.set(nb, 2); pt.set(data, 2 + nb.length);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, pt));
    const out = new Uint8Array(MAGIC.length + 12 + ct.length);
    out.set(MAGIC, 0); out.set(iv, MAGIC.length); out.set(ct, MAGIC.length + 12);
    return out;
  }
  window.__foiEncryptFile = encryptFile; // 테스트용
  window.__foiSlotFor = slotFor;

  // ---------- GitHub API ----------
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

  async function commitFiles(token, items, log) {
    log('GitHub에 암호화 파일 전송 중...');
    for (const it of items) {
      if (!it.blob) it.blob = (await gh(token, repoPath('/git/blobs'), { method: 'POST', body: { content: it.b64, encoding: 'base64' } })).sha;
    }
    for (let attempt = 1; attempt <= 3; attempt++) {
      const ref = await gh(token, repoPath(`/git/ref/heads/${REPO.branch}`));
      const base = await gh(token, repoPath(`/git/commits/${ref.object.sha}`));
      const tree = await gh(token, repoPath('/git/trees'), { method: 'POST', body: {
        base_tree: base.tree.sha,
        tree: items.map((it) => ({ path: `report_data_enc/${it.slot}.enc`, mode: '100644', type: 'blob', sha: it.blob }))
      } });
      const commit = await gh(token, repoPath('/git/commits'), { method: 'POST', body: {
        message: `data: 위탁운용 자료 업로드 (${items.map((it) => it.label).join(', ')})`, tree: tree.sha, parents: [ref.object.sha]
      } });
      try {
        await gh(token, repoPath(`/git/refs/heads/${REPO.branch}`), { method: 'PATCH', body: { sha: commit.sha, force: false } });
        return commit.sha;
      } catch (e) {
        if (e.status !== 422 || attempt === 3) throw e; // 그사이 다른 커밋이 올라온 경우 재시도
        log('다른 업데이트와 겹쳐 다시 시도합니다...');
      }
    }
  }

  async function watchRun(token, sha, log, setStatus) {
    const t0 = Date.now();
    let run = null, useToken = true;
    while (Date.now() - t0 < 15 * 60 * 1000) {
      await new Promise((r) => setTimeout(r, run ? 10000 : 6000));
      try {
        const res = await gh(useToken ? token : null, repoPath(`/actions/runs?head_sha=${sha}&per_page=5`));
        run = (res.workflow_runs || []).find((x) => /report/i.test(x.path || x.name || '')) || (res.workflow_runs || [])[0] || null;
      } catch (e) {
        if (useToken && (e.status === 403 || e.status === 401)) { useToken = false; continue; } // 토큰에 Actions 권한이 없으면 공개 API로 조회
        log('진행 상황 조회 실패: ' + e.message);
        continue;
      }
      if (!run) { setStatus('GitHub Actions 시작 대기 중...'); continue; }
      const link = `<a href="${run.html_url}" target="_blank" rel="noopener">진행 상황 보기</a>`;
      if (run.status !== 'completed') { setStatus(`보고서 생성 중 (${run.status === 'queued' ? '대기' : '실행'}) · ${link}`); continue; }
      if (run.conclusion === 'success') {
        setStatus(`✅ 보고서 생성 완료. 사이트 반영까지 1~2분 걸립니다. 잠시 후 <a href="#" onclick="location.reload();return false;">새로고침</a>해 주세요. · ${link}`);
      } else {
        setStatus(`❌ 보고서 생성 실패 (${run.conclusion}) · ${link} — 로그를 확인해 주세요.`);
      }
      return;
    }
    setStatus('진행 상황 확인 시간이 지났습니다. GitHub Actions 탭에서 확인해 주세요.');
  }

  // ---------- 화면 ----------
  function el(html) { const d = document.createElement('div'); d.innerHTML = html.trim(); return d.firstChild; }
  function openPanel() {
    let pnl = document.getElementById('upl');
    if (pnl) { pnl.style.display = 'flex'; return; }
    const saved = localStorage.getItem(TOKEN_ID) || sessionStorage.getItem(TOKEN_ID) || '';
    pnl = el(`
<div id="upl" class="upl-bg"><div class="upl">
  <div class="upl-h"><b>📤 운용 자료 업로드</b><button type="button" class="upl-x" title="닫기">✕</button></div>
  <p class="upl-d">엑셀을 올리면 브라우저에서 보고서 비밀번호로 <b>암호화</b>해 GitHub에 저장하고, GitHub Actions가 보고서를 다시 만듭니다(약 3~5분).
  같은 종류의 자료는 새 파일로 교체되고, 올리지 않은 자료는 기존 것을 그대로 사용합니다.</p>
  <label class="upl-l">엑셀 파일 (일자별 기준가 · 채권매매 손익 · 환헤지비율 · 보유내역 취합본)</label>
  <input type="file" id="upl-f" multiple accept=".xlsx,.xls">
  <ul id="upl-list" class="upl-list"></ul>
  <label class="upl-l">GitHub 토큰 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">(발급)</a>
    <span class="upl-hint">— 이 저장소만, Contents 읽기/쓰기 권한의 Fine-grained 토큰</span></label>
  <input type="password" id="upl-t" placeholder="github_pat_..." autocomplete="off">
  <label class="upl-c"><input type="checkbox" id="upl-keep" ${localStorage.getItem(TOKEN_ID) ? 'checked' : ''}> 이 브라우저에 토큰 저장</label>
  <button type="button" id="upl-go" class="upl-go" disabled>암호화 후 업로드</button>
  <div id="upl-log" class="upl-log"></div>
  <div id="upl-st" class="upl-st"></div>
</div></div>`);
    document.body.appendChild(pnl);
    const $ = (id) => document.getElementById(id);
    $('upl-t').value = saved;
    let picked = [];
    const close = () => { pnl.style.display = 'none'; };
    pnl.querySelector('.upl-x').onclick = close;
    pnl.addEventListener('click', (e) => { if (e.target === pnl) close(); });
    const log = (t) => { $('upl-log').insertAdjacentHTML('beforeend', `<div>${t}</div>`); };
    const setStatus = (h) => { $('upl-st').innerHTML = h; };

    $('upl-f').onchange = async () => {
      picked = [];
      const list = $('upl-list');
      list.innerHTML = '';
      const seen = {};
      for (const f of $('upl-f').files) {
        const name = f.name.normalize('NFC');
        const s = await slotFor(name);
        if (s && seen[s.slot]) { list.insertAdjacentHTML('beforeend', `<li class="bad">⚠ ${esc(name)} — 같은 종류(${esc(s.label)}) 파일이 이미 선택됨, 제외</li>`); continue; }
        if (s) seen[s.slot] = 1;
        list.insertAdjacentHTML('beforeend', s ? `<li>✔ ${esc(name)} <span>→ ${esc(s.label)}</span></li>` : `<li class="bad">✖ ${esc(name)} — 종류를 알 수 없음 (파일명에 기준가/매매/헤지/취합본 포함 필요)</li>`);
        if (s) picked.push({ file: f, name, slot: s.slot, label: s.label });
      }
      $('upl-go').disabled = !picked.length;
    };

    $('upl-go').onclick = async () => {
      const token = $('upl-t').value.trim();
      const keyB64 = reportKey();
      $('upl-log').innerHTML = ''; setStatus('');
      if (!token) { log('❌ GitHub 토큰을 입력해 주세요.'); return; }
      if (!keyB64) { log('❌ 로그인 정보가 없습니다. 잠금 후 다시 로그인해 주세요.'); return; }
      try {
        if ($('upl-keep').checked) { localStorage.setItem(TOKEN_ID, token); } else { localStorage.removeItem(TOKEN_ID); sessionStorage.setItem(TOKEN_ID, token); }
      } catch (e) { /* 무시 */ }
      $('upl-go').disabled = true;
      try {
        for (const it of picked) {
          log(`암호화: ${esc(it.name)}`);
          it.b64 = await toB64(await encryptFile(it.file, it.name, keyB64));
        }
        const sha = await commitFiles(token, picked, log);
        log(`✔ 업로드 완료 (커밋 ${sha.slice(0, 7)})`);
        setStatus('GitHub Actions 시작 대기 중...');
        await watchRun(token, sha, log, setStatus);
      } catch (e) {
        const m = String(e.message || e);
        let hint = '';
        if (e.status === 401) hint = ' — 토큰이 올바르지 않거나 만료되었습니다.';
        else if (e.status === 403 || e.status === 404) hint = ' — 토큰 권한을 확인해 주세요 (이 저장소, Contents: Read and write).';
        log(`❌ 업로드 실패: ${esc(m)}${hint}`);
      } finally {
        $('upl-go').disabled = !picked.length;
      }
    };
  }
  window.openUploadPanel = openPanel;
})();
