"""주간 동향 분석 탭(trends.html) 생성기.

기금운용실 보고서(주간 동향·월간 채권시장·연간 전망)를 AI 스킬로 작성한 뒤 이 도구로 등록·게시한다.
  python dashboard_trends.py add --type weekly --id 261030 --hwpx <파일.hwpx> --calc calc.json --content content.json \
         --images <그래프 폴더> [--notes notes.json]
  python dashboard_trends.py            # trends.html 다시 생성

- 원본(HWPX·본문)은 trend_reports/<type>/<id>/ 에 로컬 보관 (.gitignore, 공개 저장소에 올리지 않음)
- 게시본: trends.html (보고서 비밀번호로 암호화된 미리보기) + trend_reports_enc/<id>.enc (암호화된 HWPX, 로그인 후 다운로드)
"""
import argparse
import base64
import glob
import json
import os
import shutil
from datetime import datetime

from report_inputs import encrypt_bytes
from report_protect import _key, _password, encrypt_page

SRC_DIR, ENC_DIR, OUT = "trend_reports", "trend_reports_enc", "trends.html"
TYPES = {"weekly": "주간 동향 및 운용계획", "monthly": "월간 채권시장 동향·전망", "annual": "연간 경제·채권시장 전망"}


def cmd_add(a):
    d = os.path.join(SRC_DIR, a.type, a.id)
    os.makedirs(d, exist_ok=True)
    shutil.copy(a.hwpx, os.path.join(d, "report.hwpx"))
    meta = {"type": a.type, "id": a.id, "file": os.path.basename(a.hwpx), "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if a.calc:
        meta["calc"] = json.load(open(a.calc, encoding="utf-8"))
    if a.content:
        meta["content"] = json.load(open(a.content, encoding="utf-8"))
    if a.notes:
        meta.update(json.load(open(a.notes, encoding="utf-8")))
    if a.images:
        for p in sorted(glob.glob(os.path.join(a.images, "image*.png"))):
            shutil.copy(p, d)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("등록:", d)
    cmd_build(a)


def cmd_build(_a=None):
    key = _key(_password())
    os.makedirs(ENC_DIR, exist_ok=True)
    reports = []
    for mp in sorted(glob.glob(os.path.join(SRC_DIR, "*", "*", "meta.json"))):
        d = os.path.dirname(mp)
        m = json.load(open(mp, encoding="utf-8"))
        rid = f"{m['type']}-{m['id']}"
        with open(os.path.join(d, "report.hwpx"), "rb") as fh:
            blob = encrypt_bytes(key, m["file"], fh.read())
        with open(os.path.join(ENC_DIR, rid + ".enc"), "wb") as fh:
            fh.write(blob)
        m["rid"] = rid
        m["images"] = [base64.b64encode(open(p, "rb").read()).decode() for p in sorted(glob.glob(os.path.join(d, "image*.png")))]
        reports.append(m)
    reports.sort(key=lambda r: r["id"], reverse=True)
    data = json.dumps({"types": TYPES, "reports": reports, "gen": datetime.now().strftime("%Y-%m-%d %H:%M")},
                      ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(encrypt_page(html, "주간 동향 분석"))
    print(f"{OUT} 생성 완료(암호화): 보고서 {len(reports)}건")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>주간 동향 분석</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#f5f7fb;--card:#fff;--bd:#e2e8f0;--tx:#0f172a;--mu:#64748b;--ac:#4f46e5;--up:#dc2626;--down:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font-family:'Inter','Malgun Gothic',sans-serif;font-size:14px}
.wrap{max-width:1180px;margin:0 auto;padding:2rem 1.5rem 4rem}
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:1rem;margin-bottom:1rem}
h1{font-family:'Outfit','Malgun Gothic',sans-serif;font-size:2rem;margin:0;color:var(--ac)}
.sub{color:var(--mu);margin-top:.35rem}
.tools button{border:1px solid var(--bd);background:#fff;padding:.45rem .9rem;border-radius:8px;font-weight:600;cursor:pointer;font-family:inherit}
.tools button:hover{border-color:var(--ac);color:var(--ac)}
.seg{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem}
.seg button{border:1px solid var(--bd);background:#fff;padding:.55rem 1.1rem;border-radius:10px;font-weight:600;color:var(--mu);cursor:pointer;font-family:inherit}
.seg button.on{background:var(--ac);border-color:var(--ac);color:#fff}
.bar{display:flex;align-items:center;gap:.8rem;flex-wrap:wrap;background:#fff;border:1px solid var(--bd);border-radius:12px;padding:.8rem 1rem;margin-bottom:1rem}
.bar select{padding:.45rem .6rem;border:1px solid var(--bd);border-radius:8px;font-family:inherit;min-width:300px}
.dl{margin-left:auto;background:var(--ac);color:#fff;border:0;border-radius:9px;padding:.55rem 1.1rem;font-weight:700;cursor:pointer;font-family:inherit}
section{background:#fff;border:1px solid var(--bd);border-radius:14px;padding:1.4rem 1.6rem;margin-bottom:1rem}
h2{font-size:1.15rem;margin:0 0 .3rem}h3{font-size:.98rem;margin:1.1rem 0 .5rem;color:#334155}
.meta{color:var(--mu);font-size:.82rem}
table{width:100%;border-collapse:collapse;font-size:.88rem;margin:.4rem 0}
th{background:#f1f5f9;color:#475569;padding:.5rem .6rem;text-align:right;font-weight:600}td{padding:.5rem .6rem;text-align:right;border-bottom:1px solid #f1f5f9}
th.l,td.l{text-align:left}.up{color:var(--up);font-weight:700}.down{color:var(--down);font-weight:700}
.charts{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem}@media(max-width:900px){.charts{grid-template-columns:1fr}}
.charts figure{margin:0;border:1px solid var(--bd);border-radius:10px;padding:.5rem;background:#fff}
.charts figcaption{font-weight:700;font-size:.85rem;margin-bottom:.3rem}.charts img{width:100%;display:block}
.para{margin:.8rem 0;line-height:1.8}.para .h{font-weight:700}.para b{font-weight:700}
.note{color:#475569;font-size:.84rem;line-height:1.7;margin-left:1rem}
.summ{margin-top:.8rem;color:#334155;font-size:.88rem}
.warn{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:10px;padding:.7rem .9rem;font-size:.84rem;line-height:1.7}
.warn ul{margin:.3rem 0 0;padding-left:1.1rem}
.empty{color:var(--mu);line-height:1.9}
.src{color:var(--mu);font-size:.8rem;line-height:1.7}
@media print{.seg,.bar,.tools{display:none!important}body{background:#fff}section{border:0;padding:0}}
</style></head><body><div class="wrap">
<header><div><h1>주간 동향 분석</h1><div class="sub">기금운용실 보고서 · 주간 동향 및 운용계획 / 월간 채권시장 / 연간 전망</div></div>
<div class="tools"><button onclick="window.print()">🖨️ 인쇄</button> <button onclick="window.__reportLock && window.__reportLock()">🔒 잠금</button></div></header>
<div class="seg" id="seg"></div>
<div id="view"></div>
<p class="src" id="gen"></p>
</div>
<script>
(function () {
  const D = __DATA__;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const nf = (v, d) => Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d });
  let type = 'weekly', idx = 0;
  const NEED = {
    monthly: ['예시 양식(예시_월간_동향_및_전망_보고서.hwp 또는 hwpx) — 스킬에 내장되어 있지 않음', '월간 금리·환율 엑셀(미국10y·국고10y·국고3y·원달러·WTI, 전월말~당월말 일별)', '수익률곡선 엑셀(국고채·미국채 만기별 당월말·전월말)'],
    annual: ['증권사 연간 전망보고서 PDF (채권전략·크레딧·경제 전망 등, 여러 개)'],
    weekly: ['금리·환율 엑셀(주간동향_그래프.xlsx: 일자/환율/미국10y/한국3y)', '기준일 (YY.MM.DD)']
  };
  function seg() {
    $('#seg').innerHTML = Object.entries(D.types).map(([k, v]) => {
      const n = D.reports.filter((r) => r.type === k).length;
      return `<button data-k="${k}" class="${k === type ? 'on' : ''}">${esc(v)} (${n})</button>`;
    }).join('');
    document.querySelectorAll('#seg button').forEach((b) => b.onclick = () => { type = b.dataset.k; idx = 0; render(); });
  }
  function chg(v, unit, nd) {
    const r = Math.round(v * Math.pow(10, nd)) / Math.pow(10, nd);
    if (r === 0) return '<span>보합</span>';
    return r > 0 ? `<span class="up">+${nf(Math.abs(r), nd)}${unit}</span>` : `<span class="down">△${nf(Math.abs(r), nd)}${unit}</span>`;
  }
  function para(head, sec, tag) {
    if (!sec) return '';
    const body = sec.main.map(([k, t]) => k === 'em' ? `<b>${esc(t)}</b>` : esc(t)).join('');
    const cls = tag[1] === 'up' ? 'up' : (tag[1] === 'down' ? 'down' : '');
    const notes = (sec.notes || []).map((n) => `<div class="note">${esc(n.trim())}</div>`).join('');
    return `<div class="para"><span class="h">▪(${head})</span>${body} <span class="${cls}">(${esc(tag[0])})</span></div>${notes}`;
  }
  function weekly(r) {
    const c = r.calc, t = r.content || {};
    const rows = [['美 국채 10년(%)', c.us10y, 3, 'bp', 100], ['국고채 3년(%)', c.ktb3y, 3, 'bp', 100], ['원/달러(원)', c.usd, 1, '원', 1]];
    if (t.dxy) rows.push(['달러인덱스', t.dxy, 1, '', 1]);
    if (t.jpy) rows.push(['엔/달러', t.jpy, 1, '', 1]);
    const tb = rows.map(([n, v, d, u, k]) => `<tr><td class="l">${n}</td><td>${nf(v[0], d)}</td><td>${nf(v[1], d)}</td><td>${chg((v[1] - v[0]) * k, u, 1)}</td></tr>`).join('');
    const caps = ['미국채 10년', '국고채 3년', '원/달러'];
    const imgs = (r.images || []).map((b, i) => `<figure><figcaption>${caps[i] || ''}</figcaption><img alt="${caps[i] || ''}" src="data:image/png;base64,${b}"></figure>`).join('');
    const [u0, u1] = c.usd;
    let summ = `※ 원/달러 환율 : ${nf(u0, 1)}원 → ${nf(u1, 1)}원(${chg(u1 - u0, '원', 1)})`;
    if (t.dxy) summ += `, 달러인덱스 : ${nf(t.dxy[0], 1)} → ${nf(t.dxy[1], 1)}(${chg(t.dxy[1] - t.dxy[0], '', 1)})`;
    if (t.jpy) summ += `, 엔/달러 환율 : ${nf(t.jpy[0], 1)} → ${nf(t.jpy[1], 1)}(${chg(t.jpy[1] - t.jpy[0], '', 1)})`;
    return `<h3>주간 변동 (${esc(c.comp)} → ${esc(c.base)})</h3>
      <table><thead><tr><th class="l">지표</th><th>비교일</th><th>기준일</th><th>변동</th></tr></thead><tbody>${tb}</tbody></table>
      <h3>금주 동향 (${esc(c.trend_period)})</h3><div class="charts">${imgs}</div>
      ${para('미국금리', t.us, c.us_chg)}${para('한국금리', t.kr, c.kr_chg)}${para('원/달러 환율', t.fx, c.fx_chg)}
      <div class="summ">${summ}</div>
      <p class="meta">운용 계획 기간: ${esc(c.plan_period)} · 신규운용 현황·수익률·차주계획(운용가능 자금 등) 칸은 한글 파일에서 확인</p>`;
  }
  function render() {
    seg();
    const list = D.reports.filter((r) => r.type === type);
    if (!list.length) {
      $('#view').innerHTML = `<section><h2>${esc(D.types[type])}</h2><div class="empty">아직 등록된 보고서가 없습니다.<br>
        Antigravity에 작성을 요청하면 스킬 규칙대로 조사·작성해 이 탭에 게시합니다. 필요한 자료:<ul>${NEED[type].map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div></section>`;
      return;
    }
    const r = list[idx];
    const opts = list.map((x, i) => `<option value="${i}" ${i === idx ? 'selected' : ''}>${esc((x.calc && x.calc.title) || x.file)}</option>`).join('');
    const warn = (r.data_notes && r.data_notes.length) ? `<div class="warn"><b>데이터 확인 사항</b><ul>${r.data_notes.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
    const src = (r.sources && r.sources.length) ? `<h3>참고 자료</h3><div class="src">${r.sources.map((x) => esc(x)).join('<br>')}</div>` : '';
    $('#view').innerHTML = `<div class="bar"><select id="sel">${opts}</select><span class="meta">작성 ${esc(r.created)}</span>
      <button class="dl" id="dl">📥 한글 파일(HWPX) 다운로드</button></div>
      <section><h2>${esc((r.calc && r.calc.title) || r.file)}</h2><p class="meta">기준일 ${esc(r.calc ? r.calc.base : '')} · ${esc(r.file)}</p>
      ${warn}${type === 'weekly' && r.calc ? weekly(r) : ''}${src}</section>`;
    $('#sel').onchange = (e) => { idx = +e.target.value; render(); };
    $('#dl').onclick = () => download(r);
  }
  async function download(r) {
    const btn = $('#dl');
    try {
      const keyB64 = sessionStorage.getItem('foiReportKey') || (JSON.parse(localStorage.getItem('foiReportKey') || 'null') || {}).k;
      if (!keyB64) throw new Error('로그인 정보가 없습니다. 잠금 후 다시 로그인해 주세요.');
      btn.disabled = true; btn.textContent = '⏳ 준비 중...';
      const res = await fetch(`trend_reports_enc/${r.rid}.enc?v=${encodeURIComponent(r.created)}`);
      if (!res.ok) throw new Error('파일을 불러오지 못했습니다 (' + res.status + ')');
      const buf = new Uint8Array(await res.arrayBuffer());
      const iv = buf.slice(8, 20), ct = buf.slice(20);
      const key = await crypto.subtle.importKey('raw', Uint8Array.from(atob(keyB64), (c) => c.charCodeAt(0)), 'AES-GCM', false, ['decrypt']);
      const pt = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct));
      const n = (pt[0] << 8) | pt[1];
      const name = new TextDecoder().decode(pt.slice(2, 2 + n));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([pt.slice(2 + n)], { type: 'application/hwp+zip' }));
      a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) {
      alert('다운로드 실패: ' + (e.message || e) + (location.protocol === 'file:' ? '\n(로컬 파일에서는 브라우저가 파일 읽기를 막을 수 있습니다. 사이트 주소로 접속해 주세요.)' : ''));
    } finally {
      btn.disabled = false; btn.textContent = '📥 한글 파일(HWPX) 다운로드';
    }
  }
  $('#gen').textContent = '게시 ' + D.gen + ' · 보고서 본문은 AI가 공개 자료를 조사해 작성한 초안이므로 사실관계를 확인한 뒤 사용하세요.';
  render();
})();
</script>
</body></html>
"""

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    a = sp.add_parser("add")
    a.add_argument("--type", choices=list(TYPES), required=True)
    a.add_argument("--id", required=True)
    a.add_argument("--hwpx", required=True)
    a.add_argument("--calc"); a.add_argument("--content"); a.add_argument("--images"); a.add_argument("--notes")
    sp.add_parser("build")
    args = p.parse_args()
    cmd_add(args) if args.cmd == "add" else cmd_build(args)
