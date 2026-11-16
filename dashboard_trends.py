"""주간 동향 분석 탭(trends.html) 생성기.

기금운용실 보고서(주간 동향·월간 채권시장·연간 전망)를 AI 스킬로 작성한 뒤 이 도구로 등록·게시한다.
  python dashboard_trends.py add --type weekly --id 261030 --hwpx <파일.hwpx> --calc calc.json --content content.json \
         --images <그래프 폴더> [--notes notes.json]
  python dashboard_trends.py            # trends.html 다시 생성

- 원본(HWPX·본문)은 trend_reports/<type>/<id>/ 에 로컬 보관 (.gitignore, 공개 저장소에 올리지 않음)
- 게시본: trends.html (로그인 없이 공개) + trend_files/<type>-<id>.hwpx (다운로드용 HWPX)
"""
import argparse
import base64
import glob
import json
import os
import shutil
from datetime import datetime


SRC_DIR, PUB_DIR, OUT = "trend_reports", "trend_files", "trends.html"
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
    os.makedirs(PUB_DIR, exist_ok=True)
    reports = []
    for mp in sorted(glob.glob(os.path.join(SRC_DIR, "*", "*", "meta.json"))):
        d = os.path.dirname(mp)
        m = json.load(open(mp, encoding="utf-8"))
        rid = f"{m['type']}-{m['id']}"
        shutil.copyfile(os.path.join(d, "report.hwpx"), os.path.join(PUB_DIR, rid + ".hwpx"))
        if m["type"] == "weekly" and m.get("calc"):
            build_docx(m, d, os.path.join(PUB_DIR, rid + ".docx"))
            m["docx"] = os.path.splitext(m["file"])[0] + ".docx"
        m["rid"] = rid
        m["images"] = [base64.b64encode(open(p, "rb").read()).decode() for p in sorted(glob.glob(os.path.join(d, "image*.png")))]
        reports.append(m)
    reports.sort(key=lambda r: r["id"], reverse=True)
    data = json.dumps({"types": TYPES, "reports": reports, "gen": datetime.now().strftime("%Y-%m-%d %H:%M")},
                      ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{OUT} 생성 완료: 보고서 {len(reports)}건")


def build_docx(m, d, out):
    """주간 동향 보고서를 Word(.docx)로 저장 (HWPX와 같은 내용: 제목·그래프·본문·각주·요약·변동표)."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    RED, BLUE, GRAY = RGBColor(0xFF, 0, 0), RGBColor(0, 0, 0xFF), RGBColor(0x47, 0x55, 0x69)
    c, t = m["calc"], m.get("content") or {}
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Cm(1.5))
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "맑은 고딕", Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "맑은 고딕")
    st.paragraph_format.space_after = Pt(2)

    def run(p, text, bold=False, color=None, size=None):
        r = p.add_run(text)
        r.bold = bold
        if color is not None:
            r.font.color.rgb = color
        if size:
            r.font.size = Pt(size)
        return r

    def sign(v, unit, nd):
        v = round(v, nd)
        if v == 0:
            return "보합", None
        return (f"+{abs(v):,.{nd}f}{unit}", RED) if v > 0 else (f"△{abs(v):,.{nd}f}{unit}", BLUE)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p, c["title"], bold=True, size=16)
    p = doc.add_paragraph(); run(p, f"□ 금주 동향 ({c['trend_period']})", bold=True, size=12)

    imgs = sorted(glob.glob(os.path.join(d, "image*.png")))
    if imgs:
        caps = ["미국채 10년", "국고채 3년", "원/달러 환율"]
        tb = doc.add_table(rows=2, cols=len(imgs)); tb.style = "Table Grid"; tb.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, pth in enumerate(imgs):
            cp = tb.cell(0, i).paragraphs[0]; cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run(cp, caps[i] if i < len(caps) else "", bold=True)
            ip = tb.cell(1, i).paragraphs[0]; ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
            ip.add_run().add_picture(pth, width=Cm(8.4))
        doc.add_paragraph()

    for key, head, tag in (("us", "미국금리", c.get("us_chg")), ("kr", "한국금리", c.get("kr_chg")), ("fx", "원/달러 환율", c.get("fx_chg"))):
        s = t.get(key)
        if not s:
            continue
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(6)
        run(p, f"▪({head})", bold=True)
        for kind, text in s["main"]:
            run(p, text, bold=(kind == "em"))
        if tag:
            run(p, f" ({tag[0]})", bold=True, color=RED if tag[1] == "up" else BLUE if tag[1] == "down" else None)
        for n in s.get("notes", []):
            q = doc.add_paragraph(); q.paragraph_format.left_indent = Cm(0.6)
            run(q, n.strip(), color=GRAY, size=9.5)

    u0, u1 = c["usd"]
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(6)
    run(p, f"※ 원/달러 환율 : {u0:,.1f}원 → {u1:,.1f}원(", size=9.5)
    txt, col = sign(u1 - u0, "원", 1); run(p, txt, bold=True, color=col, size=9.5)
    for name, pair in (("달러인덱스", t.get("dxy")), ("엔/달러 환율", t.get("jpy"))):
        if pair:
            run(p, f"), {name} : {pair[0]:.1f} → {pair[1]:.1f}(", size=9.5)
            txt, col = sign(pair[1] - pair[0], "", 1); run(p, txt, bold=True, color=col, size=9.5)
    run(p, ")", size=9.5)

    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(10)
    run(p, f"□ 주간 변동 ({c['comp']} → {c['base']})", bold=True, size=12)
    rows = [("美 국채 10년(%)", c["us10y"], 3, "bp", 100), ("국고채 3년(%)", c["ktb3y"], 3, "bp", 100), ("원/달러(원)", c["usd"], 1, "원", 1)]
    if t.get("dxy"):
        rows.append(("달러인덱스", t["dxy"], 1, "", 1))
    if t.get("jpy"):
        rows.append(("엔/달러", t["jpy"], 1, "", 1))
    tb = doc.add_table(rows=1, cols=4); tb.style = "Table Grid"
    for i, h in enumerate(("지표", "비교일", "기준일", "변동")):
        run(tb.rows[0].cells[i].paragraphs[0], h, bold=True)
    for name, v, nd, unit, k in rows:
        cells = tb.add_row().cells
        cells[0].text = name
        for j, val in ((1, v[0]), (2, v[1])):
            cells[j].text = f"{val:,.{nd}f}"; cells[j].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        txt, col = sign((v[1] - v[0]) * k, unit, 1)
        cp = cells[3].paragraphs[0]; cp.alignment = WD_ALIGN_PARAGRAPH.RIGHT; run(cp, txt, bold=True, color=col)

    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(10)
    run(p, f"□ 운용 계획 ({c['plan_period']}) : 신규운용 현황·수익률·차주계획(운용가능 자금 등)은 한글(HWPX) 파일 양식을 참고하여 작성",
        color=GRAY, size=9.5)
    doc.save(out)


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
.dl2{margin-left:0!important;background:#2563eb!important}.dl{margin-left:auto;background:var(--ac);color:#fff;border:0;border-radius:9px;padding:.55rem 1.1rem;font-weight:700;cursor:pointer;font-family:inherit}
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
<div class="tools"><button onclick="window.print()">🖨️ 인쇄</button></div></header>
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
      <button class="dl" id="dl">📥 한글 파일(HWPX) 다운로드</button>${r.docx ? '<button class="dl dl2" id="dlw">📄 워드 파일(DOCX) 다운로드</button>' : ''}</div>
      <section><h2>${esc((r.calc && r.calc.title) || r.file)}</h2><p class="meta">기준일 ${esc(r.calc ? r.calc.base : '')} · ${esc(r.file)}</p>
      ${warn}${type === 'weekly' && r.calc ? weekly(r) : ''}${src}</section>`;
    $('#sel').onchange = (e) => { idx = +e.target.value; render(); };
    $('#dl').onclick = () => download(r, 'hwpx', $('#dl'));
    if (r.docx) $('#dlw').onclick = () => download(r, 'docx', $('#dlw'));
  }
  async function download(r, ext, btn) {
    const label = btn.textContent;
    const mime = ext === 'docx' ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' : 'application/hwp+zip';
    try {
      btn.disabled = true; btn.textContent = '⏳ 준비 중...';
      const res = await fetch(`trend_files/${r.rid}.${ext}?v=${encodeURIComponent(r.created)}`);
      if (!res.ok) throw new Error('파일을 불러오지 못했습니다 (' + res.status + ')');
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([await res.arrayBuffer()], { type: mime }));
      a.download = ext === 'docx' ? r.docx : r.file; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    } catch (e) {
      alert('다운로드 실패: ' + (e.message || e) + (location.protocol === 'file:' ? '\n(로컬 파일에서는 브라우저가 파일 읽기를 막을 수 있습니다. 사이트 주소로 접속해 주세요.)' : ''));
    } finally {
      btn.disabled = false; btn.textContent = label;
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
