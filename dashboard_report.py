"""위탁운용 운용분석보고서 생성기 (주간 / 월간).

report_data/ 폴더의 26년 운용자료를 읽어 기간별(주간·월간) 운용분석 결과를 계산하고
report.html 을 생성한다. 화면 렌더링은 report_app.js 가 담당한다.

입력 파일 (파일명 키워드로 탐색):
  - '기준가'  : 일자별 기준가 현황 (펀드별 기준가·BM지수·듀레이션·YTM·순자산·좌수)
  - '매매'    : 채권매매 손익률 (거래일·펀드·종목·만기·결제액·매매손익)
  - '헤지'    : 해외채권형 펀드 일자별 환헤지비율 (파일명의 운용사명 사용)
시장 데이터: 한국은행 ECOS(국고채·회사채), FRED(美국채), usd_krw_3years.csv(원/달러), spread.csv(기준금리)
"""
import glob
import io
import json
import os
import re
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BOK_API_KEY")
DATA_DIR = "report_data"
OUT_HTML = "report.html"

NAV_COLS = ["date", "name", "code", "nav", "chg", "tax_nav", "tax_chg", "adj_nav", "adj_chg", "kospi",
            "r_fund", "r_kospi", "r_ex", "aum", "units", "orig_amt", "orig",
            "w_stock", "w_bond", "w_deriv", "w_short", "dur_all", "dur_bond", "dur_bf", "bond_dur",
            "bm_idx", "ytm", "ftype", "wam", "bm_dur", "bm_ytm"]
MAT_BUCKETS = [(0, 1, "1년 미만"), (1, 3, "1~3년"), (3, 5, "3~5년"), (5, 10, "5~10년"), (10, 20, "10~20년"), (20, 99, "20년 이상")]
EOK = 1e8


# ============================================================ 데이터 로딩
def find_file(keyword):
    fs = [f for f in glob.glob(os.path.join(DATA_DIR, "*.xls*"))
          if keyword in os.path.basename(f) and not os.path.basename(f).startswith("~$")]
    return sorted(fs)[-1] if fs else None


def load_nav():
    f = find_file("기준가")
    if not f:
        raise SystemExit("report_data 폴더에 '기준가' 파일이 없습니다.")
    raw = pd.read_excel(f, header=None)
    df = raw.iloc[2:, :len(NAV_COLS)].copy()
    df.columns = NAV_COLS
    df = df[df["date"].notna() & df["code"].notna()]
    df["date"] = pd.to_datetime(df["date"])
    df["code"] = df["code"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()
    for c in NAV_COLS:
        if c not in ("date", "name", "code", "ftype"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return os.path.basename(f), df


def load_trades():
    f = find_file("매매")
    if not f:
        return None, pd.DataFrame()
    t = pd.read_excel(f)
    t = t.rename(columns={"거래일자": "date", "펀드코드": "code", "펀드명": "fname", "운용역": "pm", "자산구분": "asset",
                          "거래구분": "side", "종목코드": "isin", "종목명": "item", "상환일": "mat", "액면": "face",
                          "결제액": "amt", "매매손익": "pnl", "매매손익률": "pnl_r"})
    t["date"] = pd.to_datetime(t["date"])
    t["mat"] = pd.to_datetime(t["mat"], errors="coerce")
    t["code"] = t["code"].astype(str).str.strip()
    for c in ("face", "amt", "pnl", "pnl_r"):
        t[c] = pd.to_numeric(t[c], errors="coerce").fillna(0)
    t["mat_y"] = ((t["mat"] - t["date"]).dt.days / 365.0).clip(lower=0)
    t["bucket"] = t["mat_y"].apply(lambda m: next((b[2] for b in MAT_BUCKETS if b[0] <= m < b[1]), MAT_BUCKETS[-1][2]))
    return os.path.basename(f), t


def load_hedges():
    out = {}
    for f in glob.glob(os.path.join(DATA_DIR, "*헤지*.xls*")):
        if os.path.basename(f).startswith("~$"):
            continue
        h = pd.read_excel(f, header=None)
        m = re.search(r"\[(\w+)\]", str(h.iloc[0, 1]))
        if not m:
            continue
        mg = re.search(r"\d+년\s*(\S+?)\s*헤지", os.path.basename(f))
        d = h.iloc[2:, :4].copy()
        d.columns = ["date", "long", "short", "ratio"]
        d = d[d["date"].notna()]
        d["date"] = pd.to_datetime(d["date"])
        d["ratio"] = pd.to_numeric(d["ratio"], errors="coerce")
        out[m.group(1)] = {"mgr": mg.group(1) if mg else "", "s": d.set_index("date")["ratio"].sort_index(),
                           "file": os.path.basename(f)}
    return out


def fund_meta(name, code, hedges):
    m = re.search(r"해외\S*\s*유니버스\s*(\d+)호", name)
    if m:
        n = int(m.group(1))
        mgr = hedges.get(code, {}).get("mgr", "")
        return {"g": "O", "no": n, "t": "", "short": f"해외 {n}호", "m": mgr}
    m = re.search(r"일임\s*채권형\s*(\d+)호", name)
    if m:
        n = int(m.group(1))
        return {"g": "D", "no": n, "t": "", "short": f"일임 {n}호", "m": ""}
    m = re.search(r"유니버스\s*(\d+)호\s*\((은행|생보)\)", name)
    if m:
        n, typ = int(m.group(1)), m.group(2)
        k = (n + 1) // 2
        return {"g": "U", "no": n, "t": typ, "short": f"{n}호({typ})", "m": f"운용사 {chr(64 + k)}",
                "pair": f"{2 * k - 1}·{2 * k}호"}
    return {"g": "X", "no": 0, "t": "", "short": name, "m": ""}


# ============================================================ 시장 데이터
KTB = [("ktb1", "010190000"), ("ktb3", "010200000"), ("ktb5", "010200001"), ("ktb10", "010210000"),
       ("ktb30", "010230000"), ("corp3", "010300000")]
UST = [("ust2", "DGS2"), ("ust10", "DGS10")]


def ecos(code, start, end):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{API_KEY}/json/kr/1/1000/817Y002/D/{start:%Y%m%d}/{end:%Y%m%d}/{code}"
    rows = requests.get(url, timeout=20).json().get("StatisticSearch", {}).get("row", [])
    return pd.Series({pd.to_datetime(r["TIME"]): float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE")}, dtype=float)


def fred(sid, start, end):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start:%Y-%m-%d}&coed={end:%Y-%m-%d}"
    df = pd.read_csv(io.StringIO(requests.get(url, timeout=20).text))
    df.columns = ["d", "v"]
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    df = df.dropna()
    return pd.Series(df["v"].values, index=pd.to_datetime(df["d"]), dtype=float)


def load_market(dmin, dmax):
    start, end = dmin - pd.Timedelta(days=20), dmax
    cal = pd.date_range(start, end, freq="D")
    mk = pd.DataFrame(index=cal)
    if API_KEY:
        for k, code in KTB:
            try:
                mk[k] = ecos(code, start, end)
            except Exception as e:
                print("  ECOS 조회 실패", k, e)
    for k, sid in UST:
        try:
            mk[k] = fred(sid, start, end)
        except Exception as e:
            print("  FRED 조회 실패", k, e)
    try:
        fx = pd.read_csv("usd_krw_3years.csv")
        mk["usdkrw"] = pd.Series(pd.to_numeric(fx["15:30 종가"], errors="coerce").values, index=pd.to_datetime(fx["날짜"]))
    except Exception as e:
        print("  원/달러 로딩 실패", e)
    try:
        sp = pd.read_csv("spread.csv")
        mk["base"] = pd.Series(pd.to_numeric(sp["Base_Rate"], errors="coerce").values, index=pd.to_datetime(sp["Date"]))
    except Exception as e:
        print("  기준금리 로딩 실패", e)
    return mk.sort_index().ffill()


# ============================================================ 펀드 일별 패널
def build_funds(nav, hedges):
    funds = {}
    for code, s in nav.groupby("code"):
        s = s.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        r_nav = s["nav"].pct_change()
        r_adj = s["adj_nav"].pct_change()
        # 결산(분배) 등으로 기준가가 단절되면 수정기준가 수익률 사용
        r = r_nav.where((r_nav - r_adj).abs() < 0.0005, r_adj).fillna(0)
        s["tri"] = (1 + r).cumprod()
        s["bm"] = s["bm_idx"].where(s["bm_idx"] > 0)
        s["flow"] = s["units"].diff().fillna(0) * s["nav"] / 1000.0
        meta = fund_meta(s["name"].iloc[0], code, hedges)
        meta.update(code=code, name=s["name"].iloc[0], first=s.index[0], last=s.index[-1])
        funds[code] = {"meta": meta, "df": s}
    return funds


def pos(v):
    return v if (v is not None and not pd.isna(v) and v > 0) else None


def rnd(v, d=2):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return round(float(v), d)


# ============================================================ 기간 정의
def build_periods(dates):
    dmin, dmax = dates[0], dates[-1]
    out = {"W": [], "M": []}
    ends = [d for d in dates if d.weekday() == 4]
    if dmax.weekday() != 4:
        ends.append(dmax)
    prev = dmin
    for e in ends:
        if e <= prev:
            continue
        partial = e == dmax and e.weekday() != 4
        fri = e + pd.Timedelta(days=(4 - e.weekday()) % 7)
        nth = (fri.day - 1) // 7 + 1
        mon = max(fri - pd.Timedelta(days=4), dmin)
        rng = f"{mon.month}/{mon.day}~{e.month}/{e.day}"
        out["W"].append({"id": f"W{e:%Y%m%d}", "kind": "W", "b": prev, "e": e, "partial": partial,
                         "label": f"{fri.month}월 {nth}주차 ({rng})" + (" · 진행중" if partial else ""),
                         "title": f"{fri.year}년 {fri.month}월 {nth}주차 주간 운용분석", "range": rng})
        prev = e
    s = pd.Series(dates, index=dates)
    month_ends = s.groupby([s.index.year, s.index.month]).max().tolist()
    prev = dmin
    for e in month_ends:
        if e <= prev:
            continue
        partial = e == dmax and (e + pd.Timedelta(days=1)).month == e.month
        rng = f"{prev.month}/{prev.day}~{e.month}/{e.day}"
        out["M"].append({"id": f"M{e:%Y%m}", "kind": "M", "b": prev, "e": e, "partial": partial,
                         "label": f"{e.year}년 {e.month}월" + (f" (~{e.month}/{e.day}) · 진행중" if partial else ""),
                         "title": f"{e.year}년 {e.month}월 월간 운용분석", "range": rng})
        prev = e
    return out


# ============================================================ 기간별 계산
def fund_period(f, b, e, dmax, trades, hedges, mk):
    s, meta = f["df"], f["meta"]
    first, last = s.index[0], s.index[-1]
    if first > e or last <= b:
        return None
    bf = b if first <= b else first
    ef = min(e, last)
    new, closed = first > b, last < e
    rb_, re_ = s.loc[bf], s.loc[ef]
    win = s.loc[bf:ef]
    dt = (ef - bf).days / 365.0

    R = re_["tri"] / rb_["tri"] - 1
    Rb = (re_["bm"] / rb_["bm"] - 1) if (pd.notna(re_["bm"]) and pd.notna(rb_["bm"])) else None
    s0 = s.iloc[0]
    ytd = re_["tri"] / s0["tri"] - 1
    ytdb = (re_["bm"] / s0["bm"] - 1) if (pd.notna(re_["bm"]) and pd.notna(s0["bm"])) else None

    flow = win["flow"].iloc[1:].sum()
    aum0 = 0.0 if new else rb_["aum"]
    if new:
        flow += rb_["aum"]
    aum1 = re_["aum"]
    if closed:
        flow -= aum1
        aum1 = 0.0
    gain = aum1 - aum0 - flow

    d_e, db_e, d_b = pos(re_["dur_all"]), pos(re_["bm_dur"]), pos(rb_["dur_all"])
    y_e, yb_e = pos(re_["ytm"]), pos(re_["bm_ytm"])

    # 성과요인 분해 (추정): 초과수익 = 캐리 + 듀레이션 + 기타(커브·섹터·종목·매매)
    att = None
    ok = win[(win["dur_all"] > 0) & (win["bm_dur"] > 0) & (win["ytm"] > 0) & (win["bm_ytm"] > 0)]
    if Rb is not None and len(ok) >= 2 and bf in ok.index and ef in ok.index:
        gapD = (ok["dur_all"] - ok["bm_dur"]).mean()
        gapY = (ok["ytm"] - ok["bm_ytm"]).mean()
        dy = re_["bm_ytm"] - rb_["bm_ytm"]
        ex = (R - Rb) * 1e4
        carry = gapY * dt * 100
        dur = -gapD * dy * 100
        att = {"carry": rnd(carry, 1), "dur": rnd(dur, 1), "res": rnd(ex - carry - dur, 1),
               "gapD": rnd(gapD, 3), "gapY": rnd(gapY * 100, 1), "dy": rnd(dy * 100, 1)}

    o = {"c": meta["code"], "n": meta["short"], "g": meta["g"], "t": meta["t"], "m": meta["m"],
         "st": "신규" if new else ("해지" if closed else ""), "b": f"{bf:%Y-%m-%d}", "e": f"{ef:%Y-%m-%d}",
         "r": rnd(R * 100, 3), "rb": rnd(Rb * 100, 3) if Rb is not None else None,
         "ex": rnd((R - Rb) * 1e4, 1) if Rb is not None else None,
         "ytd": rnd(ytd * 100, 3), "ytdb": rnd(ytdb * 100, 3) if ytdb is not None else None,
         "ytdx": rnd((ytd - ytdb) * 1e4, 1) if ytdb is not None else None,
         "aum0": rnd(aum0 / EOK, 0), "aum": rnd(aum1 / EOK, 0), "aumL": rnd(re_["aum"] / EOK, 0),
         "aumavg": rnd(win["aum"].mean() / EOK, 0), "flow": rnd(flow / EOK, 0), "gain": rnd(gain / EOK, 1),
         "d": rnd(d_e, 2), "db": rnd(db_e, 2), "dg": rnd(d_e - db_e, 2) if (d_e and db_e) else None,
         "dd": rnd(d_e - d_b, 2) if (d_e and d_b) else None,
         "y": rnd(y_e, 2), "yb": rnd(yb_e, 2), "yg": rnd((y_e - yb_e) * 100, 0) if (y_e and yb_e) else None,
         "wam": rnd(re_["wam"] / 365, 2) if pos(re_["wam"]) else None,
         "wb": rnd(re_["w_bond"], 1), "ws": rnd(re_["w_short"], 1), "at": att, "first": f"{first:%Y-%m-%d}",
         "last": f"{last:%Y-%m-%d}"}

    # 매매
    if len(trades):
        t = trades[(trades["code"] == meta["code"]) & (trades["date"] > b) & (trades["date"] <= e)]
        buy, sell = t[t["side"] == "매입"], t[t["side"] == "매도"]
        if len(t):
            ba, sa = buy["amt"].sum(), sell["amt"].sum()
            o["tr"] = {"buy": rnd(ba / EOK, 1), "sell": rnd(sa / EOK, 1), "net": rnd((ba - sa) / EOK, 1),
                       "n": int(len(buy) + len(sell)), "pnl": rnd(sell["pnl"].sum() / EOK, 2),
                       "pr": rnd(sell["pnl"].sum() / sa * 100, 2) if sa else None,
                       "to": rnd((ba + sa) / 2 / win["aum"].mean() * 100, 1) if win["aum"].mean() else None,
                       "mb": rnd((buy["amt"] * buy["mat_y"]).sum() / ba, 2) if ba else None,
                       "ms": rnd((sell["amt"] * sell["mat_y"]).sum() / sa, 2) if sa else None,
                       "tin": rnd(t[t["side"] == "이수"]["amt"].sum() / EOK, 1),
                       "tout": rnd(t[t["side"] == "이체"]["amt"].sum() / EOK, 1)}

    # 해외: 환헤지
    if meta["code"] in hedges:
        hs = hedges[meta["code"]]["s"].loc[bf:ef].dropna()
        if len(hs):
            fx0, fx1 = mk["usdkrw"].asof(bf) if "usdkrw" in mk else None, mk["usdkrw"].asof(ef) if "usdkrw" in mk else None
            fxr = (fx1 / fx0 - 1) * 100 if (fx0 and fx1) else None
            med = float(hs.median())
            o["hg"] = {"end": rnd(hs.iloc[-1], 1), "start": rnd(hs.iloc[0], 1), "med": rnd(med, 1),
                       "min": rnd(hs.min(), 1), "max": rnd(hs.max(), 1), "fx": rnd(fxr, 2),
                       "fxeff": rnd((1 - med / 100) * fxr * 100, 1) if fxr is not None else None}
    return o


def wavg(items, key, wkey="aumavg"):
    xs = [(i[key], i.get(wkey) or 0) for i in items if i.get(key) is not None and (i.get(wkey) or 0) > 0]
    tw = sum(w for _, w in xs)
    return sum(v * w for v, w in xs) / tw if tw else None


def group_summary(fl):
    if not fl:
        return None
    return {"n": len(fl), "aum": rnd(sum(f["aum"] or 0 for f in fl), 0), "aum0": rnd(sum(f["aum0"] or 0 for f in fl), 0),
            "flow": rnd(sum(f["flow"] or 0 for f in fl), 0), "gain": rnd(sum(f["gain"] or 0 for f in fl), 1),
            "r": rnd(wavg(fl, "r"), 3), "rb": rnd(wavg(fl, "rb"), 3), "ex": rnd(wavg(fl, "ex"), 1),
            "ytdx": rnd(wavg(fl, "ytdx"), 1), "dg": rnd(wavg(fl, "dg"), 2),
            "nout": sum(1 for f in fl if (f.get("ex") or 0) > 0), "nbm": sum(1 for f in fl if f.get("ex") is not None)}


def market_period(mk, b, e):
    rows = []
    labels = [("base", "기준금리", "%"), ("ktb1", "국고 1년", "%"), ("ktb3", "국고 3년", "%"), ("ktb5", "국고 5년", "%"),
              ("ktb10", "국고 10년", "%"), ("ktb30", "국고 30년", "%"), ("corp3", "회사채 AA- 3년", "%"),
              ("ust2", "美국채 2년", "%"), ("ust10", "美국채 10년", "%"), ("usdkrw", "원/달러", "원")]
    vals = {}
    for k, lab, unit in labels:
        if k not in mk or mk[k].dropna().empty:
            continue
        v0, v1 = mk[k].asof(b), mk[k].asof(e)
        if pd.isna(v0) or pd.isna(v1):
            continue
        vals[k] = (v0, v1)
        ch = (v1 / v0 - 1) * 100 if unit == "원" else (v1 - v0) * 100
        rows.append({"k": k, "lab": lab, "u": unit, "s": rnd(v0, 3 if unit == "%" else 1), "e": rnd(v1, 3 if unit == "%" else 1),
                     "ch": rnd(ch, 2 if unit == "원" else 1)})
    sp = {}
    for nm, a, c in (("10-3년", "ktb10", "ktb3"), ("30-10년", "ktb30", "ktb10"), ("회사채-국고(3년)", "corp3", "ktb3")):
        if a in vals and c in vals:
            s0, s1 = (vals[a][0] - vals[c][0]) * 100, (vals[a][1] - vals[c][1]) * 100
            sp[nm] = {"s": rnd(s0, 1), "e": rnd(s1, 1), "ch": rnd(s1 - s0, 1)}
    return {"rows": rows, "sp": sp, "vals": {k: [rnd(v[0], 3), rnd(v[1], 3)] for k, v in vals.items()}}


def trade_period(trades, b, e, funds):
    if not len(trades):
        return None
    t = trades[(trades["date"] > b) & (trades["date"] <= e)]
    if not len(t):
        return {"empty": True}
    short = {c: f["meta"]["short"] for c, f in funds.items()}
    bs = t[t["side"].isin(["매입", "매도"])]
    by_asset = []
    for a, g in bs.groupby("asset"):
        ba, sa = g[g["side"] == "매입"]["amt"].sum(), g[g["side"] == "매도"]["amt"].sum()
        by_asset.append({"a": a, "buy": rnd(ba / EOK, 1), "sell": rnd(sa / EOK, 1), "net": rnd((ba - sa) / EOK, 1),
                         "pnl": rnd(g[g["side"] == "매도"]["pnl"].sum() / EOK, 2), "n": int(len(g))})
    by_asset.sort(key=lambda x: -(x["buy"] + x["sell"]))
    buckets = []
    for *_, lab in MAT_BUCKETS:
        g = bs[bs["bucket"] == lab]
        ba, sa = g[g["side"] == "매입"]["amt"].sum(), g[g["side"] == "매도"]["amt"].sum()
        buckets.append({"k": lab, "buy": rnd(ba / EOK, 1), "sell": rnd(sa / EOK, 1), "net": rnd((ba - sa) / EOK, 1)})

    def row(x):
        return {"d": f"{x['date']:%m/%d}", "f": short.get(x["code"], x["code"]), "i": str(x["item"]), "a": str(x["asset"]),
                "mat": f"{x['mat']:%Y-%m}" if pd.notna(x["mat"]) else "", "my": rnd(x["mat_y"], 1),
                "amt": rnd(x["amt"] / EOK, 1), "pnl": rnd(x["pnl"] / EOK, 2), "pr": rnd(x["pnl_r"], 2), "s": x["side"]}

    sells = bs[bs["side"] == "매도"]
    loss = sells.nsmallest(8, "pnl")
    gainr = sells[sells["pnl"] > 0].nlargest(5, "pnl")
    bigbuy = bs[bs["side"] == "매입"].nlargest(8, "amt")
    xf = t[t["side"].isin(["이수", "이체"])]
    xfer = []
    for (side, code), g in xf.groupby(["side", "code"]):
        xfer.append({"s": side, "f": short.get(code, code), "amt": rnd(g["amt"].sum() / EOK, 0), "n": int(len(g)),
                     "d": f"{g['date'].min():%m/%d}" + ("" if g["date"].min() == g["date"].max() else f"~{g['date'].max():%m/%d}")})
    ba, sa = bs[bs["side"] == "매입"]["amt"].sum(), sells["amt"].sum()
    return {"buy": rnd(ba / EOK, 0), "sell": rnd(sa / EOK, 0), "pnl": rnd(sells["pnl"].sum() / EOK, 1),
            "pr": rnd(sells["pnl"].sum() / sa * 100, 2) if sa else None, "n": int(len(bs)),
            "asset": by_asset, "bk": buckets, "loss": [row(x) for _, x in loss.iterrows() if x["pnl"] < 0],
            "gain": [row(x) for _, x in gainr.iterrows()], "bigbuy": [row(x) for _, x in bigbuy.iterrows()], "xfer": xfer}


# ============================================================ 코멘트 자동 생성
def bp(v):
    return f"{v:+.1f}bp"


def comments(p, kind):
    out, chk = [], []
    mkt, fl, gs = p["mkt"], p["funds"], p["groups"]
    v = mkt["vals"]
    # 시장
    if "ktb3" in v and "ktb10" in v:
        c3, c10 = (v["ktb3"][1] - v["ktb3"][0]) * 100, (v["ktb10"][1] - v["ktb10"][0]) * 100
        tone = "금리 상승(약세)" if c3 > 3 else ("금리 하락(강세)" if c3 < -3 else "보합권 등락")
        sp = mkt["sp"].get("10-3년")
        curve = ""
        if sp:
            curve = f", 10–3년 스프레드 {sp['e']:.0f}bp({sp['ch']:+.0f}bp, {'스티프닝' if sp['ch'] > 1 else ('플래트닝' if sp['ch'] < -1 else '보합')})"
        out.append(f"<b>시장</b>: 국고 3년 {v['ktb3'][0]:.3f}%→{v['ktb3'][1]:.3f}%({c3:+.0f}bp), 10년 {v['ktb10'][1]:.3f}%({c10:+.0f}bp)로 {tone}{curve}.")
    ext = []
    if "ust10" in v:
        ext.append(f"美국채 10년 {v['ust10'][1]:.2f}%({(v['ust10'][1] - v['ust10'][0]) * 100:+.0f}bp)")
    if "usdkrw" in v:
        ext.append(f"원/달러 {v['usdkrw'][1]:,.1f}원({(v['usdkrw'][1] / v['usdkrw'][0] - 1) * 100:+.2f}%)")
    if ext:
        out.append("<b>해외·환율</b>: " + ", ".join(ext) + ".")

    U = [f for f in fl if f["g"] == "U"]
    gu = gs.get("U")
    if gu and gu["r"] is not None:
        out.append(f"<b>국내 유니버스</b>({gu['n']}개): 가중평균 {gu['r']:.3f}% (BM {gu['rb']:.3f}%, 초과 {bp(gu['ex'])}), "
                   f"BM 상회 {gu['nout']}/{gu['nbm']}개. 연초 이후 가중평균 초과 {bp(gu['ytdx'])}.")
        ranked = sorted([f for f in U if f["ex"] is not None], key=lambda f: -f["ex"])
        if len(ranked) >= 3:
            def why(f):
                a = f.get("at")
                if not a:
                    return ""
                parts = {"듀레이션": a["dur"], "캐리": a["carry"], "기타(커브·종목·매매)": a["res"]}
                k = max(parts, key=lambda x: abs(parts[x] or 0))
                extra = f", 평균 듀레이션 갭 {a['gapD']:+.2f}년·BM금리 {a['dy']:+.0f}bp" if k == "듀레이션" else ""
                return f" – 주요인 {k} {bp(parts[k])}{extra}"
            out.append(f"<b>상위</b>: {ranked[0]['n']} {bp(ranked[0]['ex'])}{why(ranked[0])}; "
                       f"<b>하위</b>: {ranked[-1]['n']} {bp(ranked[-1]['ex'])}{why(ranked[-1])}.")
        if gu["dg"] is not None:
            out.append(f"<b>포지션</b>: 유니버스 가중평균 듀레이션 갭 {gu['dg']:+.2f}년 "
                       f"({'BM 대비 장기화' if gu['dg'] > 0.05 else ('BM 대비 단기화' if gu['dg'] < -0.05 else 'BM 중립')}).")
    # 자금
    big = [f for f in fl if f["flow"] and abs(f["flow"]) >= max(100, 0.05 * max(f["aum0"] or 0, f["aum"] or 0))]
    if big:
        big.sort(key=lambda f: -abs(f["flow"]))
        out.append("<b>자금 유출입</b>: " + ", ".join(f"{f['n']} {f['flow']:+,.0f}억" + (f"({f['st']})" if f["st"] else "") for f in big[:8]) + ".")
    tp = p.get("tr")
    if tp and not tp.get("empty"):
        out.append(f"<b>매매</b>: 매입 {tp['buy']:,.0f}억 / 매도 {tp['sell']:,.0f}억, 실현손익 {tp['pnl']:+,.1f}억"
                   + (f"(매도금액 대비 {tp['pr']:+.2f}%)" if tp["pr"] is not None else "") + ".")
        lg = [b_ for b_ in tp["bk"] if b_["k"] in ("10~20년", "20년 이상")]
        net_long = sum(b_["net"] for b_ in lg)
        if abs(net_long) >= 100:
            out.append(f"<b>만기 운용</b>: 10년 이상 구간 순{'매수' if net_long > 0 else '매도'} {abs(net_long):,.0f}억 → 장기물 {'비중 확대' if net_long > 0 else '비중 축소'} 방향.")
        if tp["xfer"]:
            out.append("<b>현물 이관</b>: " + ", ".join(f"{x['f']} {x['s']} {x['amt']:,.0f}억" for x in tp["xfer"]) + ".")
    O = [f for f in fl if f["g"] == "O"]
    if O:
        txt = []
        for f in O:
            s = f"{f['n']}{'(' + f['m'] + ')' if f['m'] else ''} {f['r']:+.2f}%"
            if f["ex"] is not None:
                s += f"(초과 {bp(f['ex'])})"
            if f.get("hg"):
                s += f", 헤지 {f['hg']['start']:.0f}%→{f['hg']['end']:.0f}%"
            txt.append(s)
        out.append("<b>해외채권형</b>: " + "; ".join(txt) + ".")
    D = [f for f in fl if f["g"] == "D"]
    if D:
        out.append("<b>일임 채권형</b>: " + ", ".join(f"{f['n']} {f['r']:+.2f}%" + (f"({f['st']} {f['last'][5:]})" if f["st"] == "해지" else "") for f in D) + ".")

    # 점검 사항
    th_ex = -10 if kind == "W" else -20
    th_to = 15 if kind == "W" else 40
    for f in fl:
        if f["dg"] is not None and abs(f["dg"]) >= 0.3:
            chk.append(f"<b>{f['n']}</b>: BM 대비 듀레이션 갭 {f['dg']:+.2f}년 → 의도된 금리 베팅인지 확인")
        if f["ex"] is not None and f["ex"] <= th_ex:
            chk.append(f"<b>{f['n']}</b>: 기간 초과수익 {bp(f['ex'])} (기준 {th_ex}bp 이하)")
        if f["ytdx"] is not None and f["ytdx"] <= -30 and f["g"] == "U":
            chk.append(f"<b>{f['n']}</b>: 연초 이후 초과수익 {bp(f['ytdx'])} 누적 부진")
        tr = f.get("tr")
        if tr and tr["pnl"] is not None and tr["pnl"] <= -10:
            chk.append(f"<b>{f['n']}</b>: 실현손실 {tr['pnl']:,.1f}억 (매도 {tr['sell']:,.0f}억)")
        if tr and tr["to"] is not None and tr["to"] >= th_to:
            chk.append(f"<b>{f['n']}</b>: 회전율 {tr['to']:.0f}% (기준 {th_to}% 이상) → 매매 사유 확인")
        if f["ws"] is not None and f["ws"] >= 5 and f["g"] != "O":
            chk.append(f"<b>{f['n']}</b>: 단기자산 비중 {f['ws']:.1f}% → 대기자금 사유 확인")
        hg = f.get("hg")
        if hg and hg["start"] is not None and abs(hg["end"] - hg["start"]) >= 10:
            chk.append(f"<b>{f['n']}</b>: 환헤지비율 {hg['start']:.0f}%→{hg['end']:.0f}% 변동")
    return out, chk


# ============================================================ 메인
def main():
    src_nav, nav = load_nav()
    src_tr, trades = load_trades()
    hedges = load_hedges()
    funds = build_funds(nav, hedges)
    dates = sorted(nav["date"].unique())
    dates = [pd.Timestamp(d) for d in dates]
    dmin, dmax = dates[0], dates[-1]
    print(f"펀드 {len(funds)}개, 기간 {dmin:%Y-%m-%d} ~ {dmax:%Y-%m-%d}, 매매 {len(trades)}건, 헤지 {len(hedges)}개")
    mk = load_market(dmin, dmax)

    periods = build_periods(dates)
    order = sorted(funds, key=lambda c: ({"U": 0, "D": 1, "O": 2}.get(funds[c]["meta"]["g"], 3), funds[c]["meta"]["no"]))
    for kind, plist in periods.items():
        for p in plist:
            b, e = p["b"], p["e"]
            fl = [x for x in (fund_period(funds[c], b, e, dmax, trades, hedges, mk) for c in order) if x]
            p["funds"] = fl
            p["groups"] = {g: group_summary([f for f in fl if f["g"] == g]) for g in ("U", "D", "O")}
            mgrs = {}
            for f in fl:
                if f["g"] == "U":
                    mgrs.setdefault(f["m"], []).append(f)
            p["mgr"] = []
            for m, fs in mgrs.items():
                trs = [f.get("tr") or {} for f in fs]
                vol = sum((t.get("buy") or 0) + (t.get("sell") or 0) for t in trs) / 2
                avg_aum = sum(f["aumavg"] or 0 for f in fs)
                p["mgr"].append(dict(m=m, funds=" · ".join(f["n"] for f in fs), **group_summary(fs),
                                     pnl=rnd(sum(t.get("pnl") or 0 for t in trs), 2),
                                     to=rnd(vol / avg_aum * 100, 1) if avg_aum else None))
            p["mkt"] = market_period(mk, b, e)
            p["tr"] = trade_period(trades, b, e, funds)
            p["cm"], p["chk"] = comments(p, kind)
            p["b"], p["e"] = f"{b:%Y-%m-%d}", f"{e:%Y-%m-%d}"

    # 일별 시계열 (차트용)
    ds = [f"{d:%Y-%m-%d}" for d in dates]
    daily = {"dates": ds, "funds": {}, "mkt": {}, "hedge": {}}
    for c in order:
        s = funds[c]["df"].reindex(dates)
        daily["funds"][c] = {"tri": [rnd(v, 6) for v in s["tri"]], "bm": [rnd(v, 4) for v in s["bm"]],
                             "dg": [rnd(a - b_, 3) if (pd.notna(a) and pd.notna(b_) and a > 0 and b_ > 0) else None
                                    for a, b_ in zip(s["dur_all"], s["bm_dur"])]}
    for k in ("ktb3", "ktb10", "ktb30", "ust10", "usdkrw"):
        if k in mk:
            daily["mkt"][k] = [rnd(v, 3) for v in mk[k].reindex(dates)]
    for c, h in hedges.items():
        daily["hedge"][c] = [rnd(v, 2) for v in h["s"].reindex(dates)]

    meta = {"gen": datetime.now().strftime("%Y-%m-%d %H:%M"), "dmin": ds[0], "dmax": ds[-1],
            "src": [x for x in [src_nav, src_tr] + [h["file"] for h in hedges.values()] if x],
            "funds": [{"c": c, "n": funds[c]["meta"]["short"], "g": funds[c]["meta"]["g"], "t": funds[c]["meta"]["t"],
                       "m": funds[c]["meta"]["m"], "pair": funds[c]["meta"].get("pair", ""),
                       "first": f"{funds[c]['meta']['first']:%Y-%m-%d}", "last": f"{funds[c]['meta']['last']:%Y-%m-%d}"}
                      for c in order]}
    for plist in periods.values():
        plist.reverse()  # 최신순
    data = {"meta": meta, "periods": periods, "daily": daily}
    js = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open("report_template.html", encoding="utf-8") as f:
        tpl = f.read()
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(tpl.replace("__REPORT_DATA__", js))
    print(f"{OUT_HTML} 생성 완료: 주간 {len(periods['W'])}개, 월간 {len(periods['M'])}개 기간 ({len(js) / 1024:,.0f}KB)")


if __name__ == "__main__":
    main()
