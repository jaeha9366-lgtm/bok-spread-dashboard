/* 주간 동향 분석 — 금리·환율 엑셀 업로드 (GitHub 로그인·토큰 불필요).
 * 대시보드 → 중계 서버(Cloudflare Worker, relay/worker.js: 업로드 비밀번호 확인) → 저장소 trend_inputs/weekly/<YYMMDD>.xlsx
 * → GitHub Actions(update_trends.yml)가 데이터 검증·AI 작성·HWPX/DOCX 게시. */
(function () {
  const RELAY = 'https://foi-trend-relay.jaeha9366.workers.dev';
  const PW_ID = 'foiTrendUploadPw';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  const css = `
.tu-bg{position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;z-index:1000;padding:1rem}
.tu{background:#fff;border-radius:14px;max-width:540px;width:100%;padding:1.3rem 1.4rem;box-shadow:0 20px 50px rgba(0,0,0,.25);max-height:92vh;overflow:auto}
.tu-h{display:flex;justify-content:space-between;align-items:center;font-size:1.05rem;margin-bottom:.4rem}
.tu-x{border:0;background:none;font-size:1.1rem;cursor:pointer;color:#64748b}
.tu-d{color:#475569;font-size:.85rem;line-height:1.7;margin:.2rem 0 .6rem}
.tu-l{display:block;font-weight:600;font-size:.85rem;margin:.8rem 0 .3rem}
.tu-hint{color:#94a3b8;font-weight:400}
.tu input[type=file],.tu input[type=password],.tu input[type=date]{width:100%;padding:.5rem;border:1px solid #e2e8f0;border-radius:8px;font-family:inherit}
.tu-c{display:flex;align-items:center;gap:.4rem;font-size:.82rem;color:#475569;margin-top:.4rem}
.tu-go{margin-top:1rem;width:100%;background:#4f46e5;color:#fff;border:0;border-radius:9px;padding:.65rem;font-weight:700;cursor:pointer;font-family:inherit}
.tu-go:disabled{opacity:.5;cursor:default}
.tu-log{margin-top:.8rem;font-size:.82rem;color:#334155;line-height:1.7}
.tu-st{margin-top:.4rem;font-size:.86rem;font-weight:600;color:#1e293b;line-height:1.7}`;

  async function relay(path, body) {
    const r = await fetch(RELAY + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
    let d = {};
    try { d = await r.json(); } catch (e) { /* 무시 */ }
    if (!r.ok) throw new Error(d.error || `중계 서버 오류 (${r.status})`);
    return d;
  }

  async function toB64(file) {
    const u8 = new Uint8Array(await file.arrayBuffer());
    let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  }

  async function watchRun(sha, setStatus) {
    const t0 = Date.now();
    while (Date.now() - t0 < 20 * 60 * 1000) {
      await new Promise((r) => setTimeout(r, 8000));
      let run = null;
      try { run = (await relay(`/status?sha=${sha}`)).run; } catch (e) { continue; }
      const min = Math.floor((Date.now() - t0) / 60000);
      if (!run) { setStatus('자동 작성 시작 대기 중...'); continue; }
      const link = `<a href="${esc(run.url)}" target="_blank" rel="noopener">진행 상황 보기</a>`;
      if (run.status !== 'completed') { setStatus(`⏳ 데이터 검증 → AI 조사·작성 → 한글 파일 생성 중 (${min}분 경과, 보통 3~6분) · ${link}`); continue; }
      if (run.conclusion === 'success') {
        setStatus(`✅ 보고서 작성 완료. 사이트 반영까지 1~2분 걸립니다. 잠시 후 <a href="#" onclick="location.reload();return false;">새로고침</a>해 주세요. · ${link}`);
      } else {
        setStatus(`❌ 보고서 작성 실패 (${esc(run.conclusion)}) · ${link} — 로그를 확인해 주세요.`);
      }
      return;
    }
    setStatus('진행 상황 확인 시간이 지났습니다. 잠시 후 새로고침해 보세요.');
  }

  function lastFriday() {
    const d = new Date();
    d.setDate(d.getDate() - ((d.getDay() + 2) % 7));
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  function openPanel() {
    let pnl = document.getElementById('tu');
    if (pnl) { pnl.style.display = 'flex'; return; }
    if (!document.getElementById('tu-css')) {
      const st = document.createElement('style'); st.id = 'tu-css'; st.textContent = css; document.head.appendChild(st);
    }
    const saved = localStorage.getItem(PW_ID) || '';
    const wrap = document.createElement('div');
    wrap.innerHTML = `
<div id="tu" class="tu-bg"><div class="tu">
  <div class="tu-h"><b>📤 주간 동향 자료 업로드</b><button type="button" class="tu-x" title="닫기">✕</button></div>
  <p class="tu-d">금리·환율 엑셀을 올리면 <b>공식 데이터와 날짜·값 대조 → AI(Gemini) 뉴스 조사·본문 작성 → 한글(HWPX)·워드 파일 생성 → 이 탭에 게시</b>까지 자동으로 진행합니다(약 3~6분).
  같은 기준일로 다시 올리면 보고서가 새로 작성됩니다.</p>
  <label class="tu-l">엑셀 파일 <span class="tu-hint">— 주간동향_그래프.xlsx (일자 / 환율 / 미국10y / 한국3y)</span></label>
  <input type="file" id="tu-f" accept=".xlsx,.xls">
  <label class="tu-l">기준일 <span class="tu-hint">— 보고서 마지막 날(보통 금요일)</span></label>
  <input type="date" id="tu-d">
  <label class="tu-l">업로드 비밀번호</label>
  <input type="password" id="tu-p" autocomplete="off">
  <label class="tu-c"><input type="checkbox" id="tu-keep" ${saved ? 'checked' : ''}> 이 브라우저에 비밀번호 저장</label>
  <button type="button" id="tu-go" class="tu-go" disabled>업로드 후 보고서 자동 작성</button>
  <div id="tu-log" class="tu-log"></div>
  <div id="tu-st" class="tu-st"></div>
</div></div>`;
    pnl = wrap.firstElementChild;
    document.body.appendChild(pnl);
    const $ = (id) => document.getElementById(id);
    $('tu-p').value = saved;
    $('tu-d').value = lastFriday();
    const close = () => { pnl.style.display = 'none'; };
    pnl.querySelector('.tu-x').onclick = close;
    pnl.addEventListener('click', (e) => { if (e.target === pnl) close(); });
    const log = (t) => { $('tu-log').insertAdjacentHTML('beforeend', `<div>${t}</div>`); };
    const setStatus = (h) => { $('tu-st').innerHTML = h; };
    const ready = () => { $('tu-go').disabled = !($('tu-f').files.length && $('tu-d').value); };
    $('tu-f').onchange = ready; $('tu-d').onchange = ready;

    $('tu-go').onclick = async () => {
      const pw = $('tu-p').value;
      const file = $('tu-f').files[0];
      const base = $('tu-d').value;
      $('tu-log').innerHTML = ''; setStatus('');
      if (!pw) { log('❌ 업로드 비밀번호를 입력해 주세요.'); return; }
      if (file.size > 6 * 1024 * 1024) { log('❌ 파일이 너무 큽니다(6MB 이하).'); return; }
      try { if ($('tu-keep').checked) localStorage.setItem(PW_ID, pw); else localStorage.removeItem(PW_ID); } catch (e) { /* 무시 */ }
      $('tu-go').disabled = true;
      try {
        log('엑셀 전송 중...');
        const r = await relay('/upload', { password: pw, base, filename: file.name.normalize('NFC'), b64: await toB64(file) });
        log(`✔ 업로드 완료 — 기준일 ${esc(base)} (${esc(r.path)})`);
        setStatus('자동 작성 시작 대기 중...');
        await watchRun(r.commit, setStatus);
      } catch (e) {
        log(`❌ 업로드 실패: ${esc(e.message || e)}`);
      } finally {
        ready();
      }
    };
  }
  window.openTrendUpload = openPanel;
})();
