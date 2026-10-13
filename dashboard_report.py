"""위탁운용 분석보고서 생성기.

report_data/ 폴더의 보유내역(집합투자증권명세 취합본) 엑셀을 읽어
운용사(펀드쌍)별 포트폴리오 분석 후 report.html 을 생성한다.
보유내역 단일 시점 자료만 있는 경우, 성과/매매 관련 섹션은 '추가 자료 필요'로 표시한다.
"""
import glob
import json
import os
import re
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BOK_API_KEY")

# 보유내역 엑셀 컬럼 인덱스 (채권 행 기준)
C_FUND, C_NAME, C_ITEM = 3, 5, 5
C_MV_OTHER = 8          # 수익증권(MMF) 평가액
C_UPNL, C_BOOK, C_MV = 35, 36, 37
C_TYPE, C_COUPON_TYPE, C_MAT = 43, 45, 49
C_COUPON = 53
C_YTM, C_DUR, C_RATING, C_SECTOR = 161, 178, 172, 181

BUCKETS = [(0, 1, "1년 미만"), (1, 3, "1~3년"), (3, 5, "3~5년"), (5, 10, "5~10년"), (10, 99, "10년 이상")]
SECTOR_KR = {"KR1_국채": "국채", "KR2_지방채": "지방채", "KR3_특수채": "특수채", "KR3_금융채": "금융채"}


def load_holdings():
    files = [f for f in glob.glob("report_data/*.xls*") if not os.path.basename(f).startswith("~$")]
    if not files:
        raise SystemExit("report_data 폴더에 엑셀 파일이 없습니다.")
    f = sorted(files)[-1]
    raw = pd.read_excel(f, header=None)
    rows = raw[raw[0].astype(str).str.isdigit()].copy()
    base_date = pd.to_datetime(rows[1].iloc[0])
    bonds = rows[rows[C_SECTOR].notna()].copy()
    others = rows[rows[C_SECTOR].isna()].copy()

    bonds["mv"] = bonds[C_MV].astype(float)
    bonds["upnl"] = bonds[C_UPNL].astype(float)
    bonds["ytm"] = bonds[C_YTM].astype(float)
    bonds["dur"] = bonds[C_DUR].astype(float)
    bonds["mat_y"] = (pd.to_datetime(bonds[C_MAT]) - base_date).dt.days / 365.0
    bonds["sector"] = bonds[C_SECTOR].map(SECTOR_KR).fillna(bonds[C_SECTOR])
    bonds["bucket"] = bonds["mat_y"].apply(lambda m: next(b[2] for b in BUCKETS if b[0] <= m < b[1]))
    bonds["issuer"] = bonds[C_NAME].astype(str).apply(issuer_of)
    others["mv"] = others[C_MV_OTHER].astype(float)
    return os.path.basename(f), base_date, bonds, others


def issuer_of(name):
    if name.startswith("국고") or "국채" in name:
        return "국고채"
    if name.startswith("국민주택"):
        return "국민주택채"
    m = re.match(r"([^\d\s]+)", name)
    return m.group(1) if m else name


def fund_no(name):
    m = re.search(r"(\d+)호", name)
    return int(m.group(1)) if m else 0


def manager_of(name):
    n = fund_no(name)
    k = (n + 1) // 2
    return f"운용사 {chr(64 + k)} ({2 * k - 1}·{2 * k}호)"


def analyze(bonds, others):
    funds = sorted(set(bonds[C_FUND]) | set(others[C_FUND]), key=fund_no)
    res = []
    for fn in funds:
        b = bonds[bonds[C_FUND] == fn]
        o = others[others[C_FUND] == fn]
        bmv, omv = b["mv"].sum(), o["mv"].sum()
        tot = bmv + omv
        w = b["mv"] / bmv if bmv else 0
        dur = float((b["dur"] * w).sum())
        buckets = {lab: float(b.loc[b["bucket"] == lab, "mv"].sum() / bmv * 100) for *_, lab in BUCKETS}
        sectors = (b.groupby("sector")["mv"].sum() / bmv * 100).to_dict()
        issuers = (b.groupby("issuer")["mv"].sum() / tot * 100).sort_values(ascending=False)
        non_gov = issuers.drop(labels=["국고채", "국민주택채"], errors="ignore")
        # 듀레이션 기여도(만기구간별)
        dur_contrib = {lab: float((b.loc[b["bucket"] == lab, "dur"] * w[b["bucket"] == lab]).sum()) for *_, lab in BUCKETS}
        res.append({
            "fund": fn,
            "short": fn.replace("예금보험기금유니버스", ""),
            "no": fund_no(fn),
            "type": "은행" if "은행" in fn else "생보",
            "manager": manager_of(fn),
            "total": tot, "bond_mv": bmv, "cash_mv": omv,
            "cash_w": omv / tot * 100 if tot else 0,
            "dur": dur,
            "dur_total": dur * bmv / tot if tot else 0,
            "ytm": float((b["ytm"] * w).sum()),
            "mat": float((b["mat_y"] * w).sum()),
            "n": len(b),
            "aaa_w": float(b.loc[b[C_RATING] == "AAA", "mv"].sum() / bmv * 100),
            "upnl": b["upnl"].sum(),
            "dv01": float((b["mv"] * b["dur"]).sum() * 0.0001),
            "buckets": buckets, "dur_contrib": dur_contrib,
            "sectors": {k: float(v) for k, v in sectors.items()},
            "top_issuers": [(k, float(v)) for k, v in non_gov.head(3).items()],
            "max_issue": b.assign(wt=b["mv"] / tot * 100).sort_values("wt", ascending=False)[[C_NAME, "wt", "dur"]].head(3).values.tolist(),
            "long_w": buckets["5~10년"] + buckets["10년 이상"],
        })
    return res


# ---------------- 시장 금리 커브 ----------------
KTB_CODES = [("1Y", "010190000"), ("2Y", "010195000"), ("3Y", "010200000"), ("5Y", "010200001"),
             ("10Y", "010210000"), ("20Y", "010220000"), ("30Y", "010230000")]
UST_CODES = [("3M", "DGS3MO"), ("1Y", "DGS1"), ("2Y", "DGS2"), ("5Y", "DGS5"), ("10Y", "DGS10"), ("30Y", "DGS30")]


def as_of(series, date):
    s = {k: v for k, v in series.items() if k <= date}
    return s[max(s)] if s else None


def fetch_curves(dates):
    ktb, ust = {}, {}
    start = (min(dates) - pd.Timedelta(days=15)).strftime("%Y%m%d")
    end = max(dates).strftime("%Y%m%d")
    if API_KEY:
        for tenor, code in KTB_CODES:
            try:
                url = f"https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/1/2000/817Y002/D/{start}/{end}/{code}"
                rows = requests.get(url, timeout=20).json().get("StatisticSearch", {}).get("row", [])
                ser = {r["TIME"]: float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE")}
                ktb[tenor] = {d.strftime("%Y-%m-%d"): as_of(ser, d.strftime("%Y%m%d")) for d in dates}
            except Exception as e:
                print("KTB fetch fail", tenor, e)
    for tenor, code in UST_CODES:
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}&cosd={min(dates) - pd.Timedelta(days=15):%Y-%m-%d}&coed={max(dates):%Y-%m-%d}"
            df = pd.read_csv(url)
            df.columns = ["d", "v"]
            df["v"] = pd.to_numeric(df["v"], errors="coerce")
            ser = {r.d.replace("-", ""): r.v for r in df.dropna().itertuples()}
            ust[tenor] = {d.strftime("%Y-%m-%d"): as_of(ser, d.strftime("%Y%m%d")) for d in dates}
        except Exception as e:
            print("UST fetch fail", tenor, e)
    return ktb, ust


# ---------------- HTML ----------------
def fmt_eok(v):
    return f"{v / 1e8:,.0f}"


def cls_num(v):
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def build_html(src, base_date, res, ktb, ust, dates):
    date_s = base_date.strftime("%Y.%m.%d")
    mgrs = {}
    for r in res:
        mgrs.setdefault(r["manager"], []).append(r)
    tot_aum = sum(r["total"] for r in res)
    avg = lambda key, sub: sum(r[key] * r["bond_mv"] for r in sub) / sum(r["bond_mv"] for r in sub)
    bank = [r for r in res if r["type"] == "은행"]
    life = [r for r in res if r["type"] == "생보"]
    bank_dur, life_dur = avg("dur", bank), avg("dur", life)
    all_dur, all_ytm = avg("dur", res), avg("ytm", res)

    def style_of(r):
        peer = bank_dur if r["type"] == "은행" else life_dur
        gap = r["dur"] - peer
        if gap > 0.3:
            s = "장기화(Long)"
        elif gap < -0.3:
            s = "단기화(Short)"
        else:
            s = "중립(Neutral)"
        bar = "바벨형" if (r["buckets"]["1년 미만"] + r["buckets"]["1~3년"]) > 30 and r["long_w"] > 40 else (
            "장기집중형" if r["long_w"] > 55 else ("불릿형" if max(r["buckets"].values()) > 45 else "분산형"))
        return s, bar, gap

    # ---- 1. 요약 KPI
    kpi = f"""
    <div class="kpis">
      <div class="kpi"><div class="kl">총 운용규모</div><div class="kv">{tot_aum / 1e12:,.2f}<small>조원</small></div><div class="ks">12개 펀드 · 6개 운용사</div></div>
      <div class="kpi"><div class="kl">가중평균 듀레이션</div><div class="kv">{all_dur:.2f}<small>년</small></div><div class="ks">은행형 {bank_dur:.2f} / 생보형 {life_dur:.2f}</div></div>
      <div class="kpi"><div class="kl">가중평균 시가 YTM</div><div class="kv">{all_ytm:.2f}<small>%</small></div><div class="ks">채권 평가액 기준</div></div>
      <div class="kpi"><div class="kl">평가손익 합계</div><div class="kv {cls_num(sum(r['upnl'] for r in res))}">{sum(r['upnl'] for r in res) / 1e8:,.0f}<small>억원</small></div><div class="ks">장부가 대비 시가</div></div>
      <div class="kpi"><div class="kl">DV01 (1bp)</div><div class="kv">{sum(r['dv01'] for r in res) / 1e8:,.2f}<small>억원</small></div><div class="ks">금리 1bp 상승 시 평가손실</div></div>
    </div>"""

    style_rows = ""
    for r in res:
        s, bar, gap = style_of(r)
        tag = "long" if "Long" in s else ("short" if "Short" in s else "neu")
        style_rows += f"""<tr><td class="l">{r['manager']}</td><td class="l">{r['short']}</td><td>{r['type']}</td>
          <td>{fmt_eok(r['total'])}</td><td><b>{r['dur']:.2f}</b></td><td class="{cls_num(gap)}">{gap:+.2f}</td>
          <td>{r['ytm']:.3f}</td><td>{r['mat']:.2f}</td><td>{r['cash_w']:.1f}%</td>
          <td><span class="tag {tag}">{s}</span></td><td>{bar}</td></tr>"""

    longest = max(res, key=lambda r: r["dur"])
    shortest = min(res, key=lambda r: r["dur"])
    best_y = max(res, key=lambda r: r["ytm"])
    summary_points = f"""
    <ul class="pts">
      <li><b>기간성과·원인분석</b>: 제공 자료가 {date_s} 단일 시점 보유내역이므로 수익률·BM대비 성과는 산출 불가 → 아래 표의 <b>평가손익(장부가 대비)</b>과 <b>금리 민감도</b>로 대체 진단.</li>
      <li><b>듀레이션</b>: 전체 {all_dur:.2f}년. 최장 <b>{longest['short']}</b>({longest['dur']:.2f}년), 최단 <b>{shortest['short']}</b>({shortest['dur']:.2f}년)로 펀드 간 격차 {longest['dur'] - shortest['dur']:.2f}년.
          생보형 평균({life_dur:.2f}년)이 은행형({bank_dur:.2f}년)보다 {'길어' if life_dur > bank_dur else '짧아'} 유형별 BM 차이가 반영된 것으로 판단.</li>
      <li><b>캐리(수익원)</b>: 시가 YTM 최고는 <b>{best_y['short']}</b>({best_y['ytm']:.3f}%). 특수채·지방채 비중이 높을수록 YTM 우위.</li>
      <li><b>BM대비 요인분해</b>: BM 구성(듀레이션·섹터) 자료 수령 시 듀레이션/커브/섹터/종목 효과로 분해 예정. 현재는 동일 유형 펀드 평균을 Peer BM으로 사용.</li>
    </ul>"""

    # ---- 2. 듀레이션 표
    dur_rows = ""
    for m, fs in mgrs.items():
        for i, r in enumerate(fs):
            dur_rows += f"<tr>{f'<td class=l rowspan={len(fs)}>{m}</td>' if i == 0 else ''}<td class='l'>{r['short']}</td><td><b>{r['dur']:.2f}</b></td><td>{r['dur_total']:.2f}</td>" + \
                        "".join(f"<td>{r['dur_contrib'][lab]:.2f}</td>" for *_, lab in BUCKETS) + "</tr>"

    # ---- 4. 금리 커브
    curve_tbl = ""
    curve_js = {"ktb": {}, "ust": {}}
    dlabels = [d.strftime("%Y-%m-%d") for d in dates]
    for name, data, key in (("국고채", ktb, "ktb"), ("美국채", ust, "ust")):
        if not data:
            curve_tbl += f"<p class='muted'>{name} 금리 데이터를 불러오지 못했습니다.</p>"
            continue
        tenors = list(data.keys())
        head = "".join(f"<th>{t}</th>" for t in tenors)
        body = ""
        for d in dlabels:
            body += f"<tr><td class='l'>{d}</td>" + "".join(f"<td>{data[t][d]:.3f}</td>" if data[t][d] is not None else "<td>-</td>" for t in tenors) + "</tr>"
            curve_js[key][d] = [data[t][d] for t in tenors]
        first, last = dlabels[0], dlabels[-1]
        chg = "".join(
            f"<td class='{cls_num((data[t][last] or 0) - (data[t][first] or 0))}'>{((data[t][last] or 0) - (data[t][first] or 0)) * 100:+.0f}bp</td>" for t in tenors)
        body += f"<tr class='sum'><td class='l'>변화({first[:7]}→{last[:7]})</td>{chg}</tr>"
        curve_tbl += f"<h3>{name} 만기구간별 금리 (%)</h3><table><thead><tr><th class='l'>기준일</th>{head}</tr></thead><tbody>{body}</tbody></table>"
        curve_js[key + "_t"] = tenors

    def spread_txt(data, a, b):
        try:
            return (data[b][dlabels[-1]] - data[a][dlabels[-1]]) * 100
        except Exception:
            return None
    k_sp, u_sp = spread_txt(ktb, "3Y", "10Y"), spread_txt(ust, "2Y", "10Y")
    curve_comment = "<ul class='pts'>"
    if k_sp is not None:
        curve_comment += f"<li>국고 3–10년 스프레드 {k_sp:.0f}bp: {'커브 스티프닝 구간으로 장기물 캐리·롤다운 유리' if k_sp > 30 else '커브 플랫 구간으로 장기 연장의 보상 제한적'}.</li>"
    if u_sp is not None:
        curve_comment += f"<li>美국채 2–10년 스프레드 {u_sp:.0f}bp: 글로벌 장기금리 방향이 국내 장기물(10년 이상)에 전이될 수 있어 장기집중 펀드 모니터링 필요.</li>"
    curve_comment += "</ul>"

    # ---- 5. 만기구간 비중
    bucket_head = "".join(f"<th>{lab}</th>" for *_, lab in BUCKETS)
    bucket_rows = ""
    for r in res:
        mx = max(r["buckets"].values())
        bucket_rows += f"<tr><td class='l'>{r['short']}</td>" + "".join(
            f"<td class='{'hl' if v == mx else ''}'><div class='cell-bar' style='--w:{v:.0f}%'></div>{v:.1f}%</td>" for v in r["buckets"].values()) + \
            f"<td>{r['sectors'].get('국채', 0):.1f}%</td><td>{r['sectors'].get('특수채', 0):.1f}%</td><td>{r['sectors'].get('지방채', 0):.1f}%</td><td>{r['sectors'].get('금융채', 0):.1f}%</td></tr>"

    detail_cards = ""
    for m, fs in mgrs.items():
        inner = ""
        for r in fs:
            s, bar, gap = style_of(r)
            top_bucket = max(r["buckets"], key=r["buckets"].get)
            main_contrib = max(r["dur_contrib"], key=r["dur_contrib"].get)
            iss = ", ".join(f"{k} {v:.1f}%" for k, v in r["top_issuers"]) or "-"
            big = r["max_issue"][0]
            shock = -r["dv01"] * 50 / 1e8
            inner += f"""<div class="fund">
              <div class="fh"><b>{r['short']}</b><span class="tag {'long' if 'Long' in s else 'short' if 'Short' in s else 'neu'}">{s}</span></div>
              <ul>
                <li><b>듀레이션 효과</b>: {r['dur']:.2f}년 (Peer 대비 {gap:+.2f}년). 금리 50bp 상승 시 약 <span class="neg">{shock:,.0f}억원</span> 평가손 (DV01 {r['dv01'] / 1e8:,.2f}억).</li>
                <li><b>만기 효과</b>: {top_bucket} 구간 비중 최대({r['buckets'][top_bucket]:.1f}%), 듀레이션 기여는 {main_contrib}({r['dur_contrib'][main_contrib]:.2f}년)에 집중 → {bar}.</li>
                <li><b>섹터·신용</b>: 국채 {r['sectors'].get('국채', 0):.1f}% / 비국채 {100 - r['sectors'].get('국채', 0):.1f}%, AAA {r['aaa_w']:.1f}%. 비국채 상위 발행사: {iss}.</li>
                <li><b>종목 집중</b>: 최대 종목 {big[0]} ({big[1]:.1f}%, 듀레이션 {big[2]:.2f}). 보유 {r['n']}종목, 유동성(MMF) {r['cash_w']:.1f}%.</li>
                <li><b>평가손익</b>: <span class="{cls_num(r['upnl'])}">{r['upnl'] / 1e8:+,.1f}억원</span> · 시가 YTM {r['ytm']:.3f}%.</li>
              </ul></div>"""
        detail_cards += f"<div class='mgr'><h3>{m}</h3><div class='fgrid'>{inner}</div></div>"

    # ---- 6. 종합
    checks = []
    for r in res:
        s, bar, gap = style_of(r)
        if abs(gap) > 0.5:
            checks.append(f"<b>{r['short']}</b>: Peer 대비 듀레이션 {gap:+.2f}년 괴리 → BM 대비 의도된 베팅인지 운용사 확인")
        if r["cash_w"] > 5:
            checks.append(f"<b>{r['short']}</b>: 유동성(MMF) {r['cash_w']:.1f}% → 캐리 손실 요인, 대기자금 사유 확인")
        if r["buckets"]["10년 이상"] > 25:
            checks.append(f"<b>{r['short']}</b>: 10년 이상 비중 {r['buckets']['10년 이상']:.1f}% → 장기금리 변동성 노출 큼")
        if r["max_issue"][0][1] > 15:
            checks.append(f"<b>{r['short']}</b>: 단일종목 {r['max_issue'][0][0]} {r['max_issue'][0][1]:.1f}% 집중")
    checks_html = "".join(f"<li>{c}</li>" for c in checks) or "<li>특이 점검사항 없음</li>"
    mgr_rank = sorted(((m, sum(r['ytm'] * r['bond_mv'] for r in fs) / sum(r['bond_mv'] for r in fs),
                        sum(r['dur'] * r['bond_mv'] for r in fs) / sum(r['bond_mv'] for r in fs)) for m, fs in mgrs.items()),
                      key=lambda x: -x[1])
    rank_rows = "".join(f"<tr><td>{i + 1}</td><td class='l'>{m}</td><td>{y:.3f}%</td><td>{d:.2f}</td><td>{y / d * 100 if d else 0:.1f}</td></tr>" for i, (m, y, d) in enumerate(mgr_rank))

    chart_data = {
        "labels": [r["short"] for r in res],
        "dur": [round(r["dur"], 3) for r in res],
        "ytm": [round(r["ytm"], 3) for r in res],
        "buckets": {lab: [round(r["buckets"][lab], 2) for r in res] for *_, lab in BUCKETS},
        "curve": curve_js, "dates": dlabels,
        "peer": [round(bank_dur if r["type"] == "은행" else life_dur, 3) for r in res],
    }

    need = lambda items: "<div class='need'><b>📎 추가 자료 필요</b><ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>"

    return TEMPLATE.format(
        date=date_s, src=src, gen=datetime.now().strftime("%Y-%m-%d %H:%M"),
        kpi=kpi, summary_points=summary_points, style_rows=style_rows,
        dur_rows=dur_rows, bucket_head_contrib="".join(f"<th>{lab}</th>" for *_, lab in BUCKETS),
        need2=need(["월말(또는 분기말) 보유내역 → 듀레이션 '추이' 산출"]),
        need3=need(["펀드별 월별 기준가/수익률", "BM 지수 및 월별 BM 수익률"]),
        curve_tbl=curve_tbl, curve_comment=curve_comment,
        bucket_head=bucket_head, bucket_rows=bucket_rows,
        need5=need(["기초 시점(예: 6월말) 보유내역 → 만기구간 비중 '변화' 산출"]),
        detail_cards=detail_cards, checks_html=checks_html, rank_rows=rank_rows,
        need7=need(["기간 중 매매내역(체결일·종목·수량·단가)", "실현손익 내역"]),
        chart_json=json.dumps(chart_data, ensure_ascii=False),
        life_dur=f"{life_dur:.2f}", bank_dur=f"{bank_dur:.2f}",
    )


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>위탁운용 분석보고서 ({date})</title>
<meta name="description" content="예금보험기금 국내채권형 위탁운용 펀드 운용사별 듀레이션·만기구간·섹터·금리민감도 분석보고서">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--bd:#e2e8f0;--tx:#0f172a;--mu:#64748b;--ac:#4f46e5;--ac2:#0ea5e9;--pos:#dc2626;--neg:#2563eb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font-family:'Inter',sans-serif;font-size:14px}}
.wrap{{max-width:1280px;margin:0 auto;padding:2.2rem 1.5rem 4rem}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;margin-bottom:1.5rem;flex-wrap:wrap}}
h1{{font-family:'Outfit',sans-serif;font-size:2rem;margin:0;background:linear-gradient(135deg,var(--ac),var(--ac2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:var(--mu);margin-top:.35rem}}.badge{{background:#eef2ff;color:var(--ac);padding:.45rem 1rem;border-radius:999px;font-weight:600;font-size:.85rem}}
.toc{{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1.5rem;position:sticky;top:0;background:var(--bg);padding:.6rem 0;z-index:5}}
.toc a{{text-decoration:none;color:var(--mu);background:var(--card);border:1px solid var(--bd);padding:.4rem .85rem;border-radius:8px;font-size:.82rem;font-weight:500;transition:all .2s}}
.toc a:hover{{color:var(--ac);border-color:var(--ac);transform:translateY(-1px)}}
section{{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:1.6rem 1.8rem;margin-bottom:1.2rem;box-shadow:0 2px 10px rgba(15,23,42,.04);animation:fade .5s ease both}}
@keyframes fade{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1}}}}
h2{{font-family:'Outfit',sans-serif;font-size:1.3rem;margin:0 0 1rem}}h2 span{{color:var(--ac);margin-right:.4rem}}
h3{{font-size:1rem;margin:1.3rem 0 .6rem;color:#334155}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.8rem;margin-bottom:1.2rem}}
.kpi{{background:linear-gradient(135deg,#f8faff,#eef2ff);border:1px solid #e0e7ff;border-radius:12px;padding:1rem 1.1rem;transition:transform .2s}}
.kpi:hover{{transform:translateY(-2px)}}.kl{{color:var(--mu);font-size:.8rem;font-weight:600}}
.kv{{font-family:'Outfit',sans-serif;font-size:1.7rem;font-weight:700;margin:.2rem 0}}.kv small{{font-size:.85rem;margin-left:.2rem;color:var(--mu)}}.ks{{color:var(--mu);font-size:.78rem}}
table{{width:100%;border-collapse:collapse;font-size:.85rem;margin:.3rem 0 .8rem}}
th{{background:#f1f5f9;color:#475569;font-weight:600;padding:.55rem .6rem;text-align:right;border-bottom:1px solid var(--bd);white-space:nowrap}}
td{{padding:.5rem .6rem;text-align:right;border-bottom:1px solid #f1f5f9;position:relative}}
th.l,td.l{{text-align:left}}table.nowrap td,table.nowrap th{{white-space:nowrap}}tbody tr:hover td{{background:#f8fafc}}tr.sum td{{font-weight:600;background:#fafafa}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.muted{{color:var(--mu)}}
td.hl{{font-weight:700;color:var(--ac)}}
.cell-bar{{position:absolute;left:0;top:20%;height:60%;width:var(--w);background:rgba(79,70,229,.08);border-radius:3px;max-width:100%}}
.tag{{padding:.18rem .55rem;border-radius:6px;font-size:.75rem;font-weight:600;white-space:nowrap}}
.tag.long{{background:#fee2e2;color:#b91c1c}}.tag.short{{background:#dbeafe;color:#1d4ed8}}.tag.neu{{background:#f1f5f9;color:#475569}}
.pts{{line-height:1.85;padding-left:1.2rem;margin:.4rem 0}}
.need{{margin-top:1rem;padding:.9rem 1.1rem;border:1.5px dashed #cbd5e1;border-radius:10px;background:#fcfcfd;color:var(--mu);font-size:.85rem}}
.need ul{{margin:.4rem 0 0;padding-left:1.2rem}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem}}@media(max-width:900px){{.grid2{{grid-template-columns:1fr}}}}
.chart{{position:relative;height:300px}}
.mgr{{margin-top:1.2rem}}.fgrid{{display:grid;grid-template-columns:1fr 1fr;gap:.9rem}}@media(max-width:900px){{.fgrid{{grid-template-columns:1fr}}}}
.fund{{border:1px solid var(--bd);border-radius:12px;padding:1rem 1.1rem;transition:box-shadow .2s}}.fund:hover{{box-shadow:0 6px 20px rgba(79,70,229,.08)}}
.fh{{display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem}}.fund ul{{margin:0;padding-left:1.1rem;line-height:1.75;font-size:.85rem}}
.note{{color:var(--mu);font-size:.78rem;margin-top:.4rem}}
footer{{color:var(--mu);font-size:.78rem;text-align:center;margin-top:2rem}}
</style></head><body><div class="wrap">
<header><div><h1>위탁운용 분석보고서</h1><div class="sub">예금보험기금 국내채권형 유니버스 1~12호 · 운용사별 포트폴리오 분석</div></div>
<div class="badge">기준일 {date}</div></header>
<nav class="toc"><a href="#s1">1. 요약</a><a href="#s2">2. 듀레이션</a><a href="#s3">3. 누적 수익률</a><a href="#s4">4. 금리 커브</a><a href="#s5">5. 펀드별 비교</a><a href="#s6">6. 종합·시사점</a><a href="#s7">7. 매매·실현손익</a></nav>

<section id="s1"><h2><span>1.</span>요약</h2>{kpi}{summary_points}
<h3>펀드별 듀레이션 운용 스타일 (Peer = 동일 유형 평균: 은행형 {bank_dur}년 / 생보형 {life_dur}년)</h3>
<table><thead><tr><th class="l">운용사</th><th class="l">펀드</th><th>유형</th><th>운용규모(억)</th><th>듀레이션</th><th>Peer 대비</th><th>시가YTM(%)</th><th>잔존만기(년)</th><th>유동성</th><th>스타일</th><th>만기구조</th></tr></thead><tbody>{style_rows}</tbody></table>
<div class="note">※ 운용사명은 펀드 코드쌍(1·2호, 3·4호 …) 기준 추정 표기. 실제 운용사명 제공 시 반영.</div></section>

<section id="s2"><h2><span>2.</span>펀드별 월말 듀레이션</h2>
<div class="chart" style="height:280px;margin-bottom:1rem"><canvas id="cDur"></canvas></div>
<div style="overflow-x:auto"><table class="nowrap"><thead><tr><th class="l">운용사</th><th class="l">펀드</th><th>채권 듀레이션</th><th>펀드 듀레이션(MMF 포함)</th>{bucket_head_contrib}</tr></thead><tbody>{dur_rows}</tbody></table></div>
<div class="note">※ 만기구간 열 = 해당 구간의 듀레이션 기여도(년). 합계 = 채권 듀레이션.</div>{need2}</section>

<section id="s3"><h2><span>3.</span>누적 수익률 (기간별)</h2><p class="muted">보유내역 단일 시점 자료로는 기간 수익률 산출이 불가합니다.</p>{need3}</section>

<section id="s4"><h2><span>4.</span>시장 환경 : 금리 커브</h2>
<div class="grid2"><div class="chart"><canvas id="cKtb"></canvas></div><div class="chart"><canvas id="cUst"></canvas></div></div>
{curve_tbl}{curve_comment}</section>

<section id="s5"><h2><span>5.</span>펀드별 비교 분석</h2>
<h3>[표] 펀드별 만기구간별 비중 (채권 평가액 기준, {date})</h3>
<table><thead><tr><th class="l">펀드</th>{bucket_head}<th>국채</th><th>특수채</th><th>지방채</th><th>금융채</th></tr></thead><tbody>{bucket_rows}</tbody></table>
<div class="chart" style="height:340px"><canvas id="cBucket"></canvas></div>{need5}
<h3>펀드별 상세 분석</h3>{detail_cards}</section>

<section id="s6"><h2><span>6.</span>종합 및 시사점</h2>
<h3>성과 귀속 (캐리 관점, 운용사별)</h3>
<table><thead><tr><th>순위</th><th class="l">운용사</th><th>가중 시가YTM</th><th>듀레이션</th><th>YTM/듀레이션(bp/년)</th></tr></thead><tbody>{rank_rows}</tbody></table>
<div class="note">※ YTM/듀레이션 = 듀레이션 1년당 확보한 캐리 → 금리위험 대비 효율성 지표.</div>
<h3>듀레이션 판단</h3><ul class="pts"><li>생보형은 부채 듀레이션 매칭 목적상 장기, 은행형은 중단기 운용이 기본. 동일 유형 내 괴리가 큰 펀드는 BM 대비 액티브 베팅 여부 확인 필요.</li>
<li>현 커브 기울기에서 장기 연장은 캐리·롤다운 이익이 있으나, 금리 반등 시 손실 폭이 크므로 DV01 한도 점검 권고.</li></ul>
<h3>점검 필요사항</h3><ul class="pts">{checks_html}</ul></section>

<section id="s7"><h2><span>7.</span>기간 중 매매 규모 및 실현 손익</h2><p class="muted">보유내역 자료에는 매매내역이 포함되어 있지 않습니다.</p>{need7}</section>
<footer>원자료: {src} · 생성: {gen} · 금리: 한국은행 ECOS / FRED</footer></div>
<script>
const D={chart_json};
Chart.defaults.font.family="Inter";Chart.defaults.color="#64748b";
new Chart(cDur,{{type:'bar',data:{{labels:D.labels,datasets:[{{label:'듀레이션',data:D.dur,backgroundColor:'rgba(79,70,229,.75)',borderRadius:6}},{{label:'Peer 평균',data:D.peer,type:'line',borderColor:'#f59e0b',pointRadius:0,borderDash:[5,4]}}]}},options:{{maintainAspectRatio:false,plugins:{{title:{{display:true,text:'펀드별 듀레이션 vs Peer'}}}}}}}});
const cols=['#c7d2fe','#93c5fd','#60a5fa','#4f46e5','#312e81'];
new Chart(cBucket,{{type:'bar',data:{{labels:D.labels,datasets:Object.keys(D.buckets).map((k,i)=>({{label:k,data:D.buckets[k],backgroundColor:cols[i]}}))}},options:{{maintainAspectRatio:false,scales:{{x:{{stacked:true}},y:{{stacked:true,max:100,ticks:{{callback:v=>v+'%'}}}}}},plugins:{{title:{{display:true,text:'만기구간별 비중'}}}}}}}});
const lc=['#cbd5e1','#94a3b8','#0ea5e9','#4f46e5'];
function curve(el,key,title){{const c=D.curve[key];if(!c||!D.curve[key+'_t'])return;new Chart(el,{{type:'line',data:{{labels:D.curve[key+'_t'],datasets:Object.keys(c).map((d,i)=>({{label:d,data:c[d],borderColor:lc[i%4],backgroundColor:lc[i%4],tension:.3,borderWidth:i==Object.keys(c).length-1?3:2}}))}},options:{{maintainAspectRatio:false,plugins:{{title:{{display:true,text:title}}}},scales:{{y:{{ticks:{{callback:v=>v.toFixed(2)+'%'}}}}}}}}}});}}
curve(cKtb,'ktb','국고채 금리 커브');curve(cUst,'ust','美국채 금리 커브');
</script></body></html>"""


def main():
    src, base_date, bonds, others = load_holdings()
    res = analyze(bonds, others)
    dates = [base_date - pd.DateOffset(years=1), base_date - pd.DateOffset(months=6), base_date - pd.DateOffset(months=3), base_date]
    dates = [pd.Timestamp(d) + pd.offsets.MonthEnd(0) for d in dates]
    ktb, ust = fetch_curves(dates)
    html = build_html(src, base_date, res, ktb, ust, dates)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"report.html 생성 완료 ({len(res)}개 펀드, 기준일 {base_date:%Y-%m-%d})")


if __name__ == "__main__":
    main()
