"""주간 동향 보고서 자동 작성 — 대시보드 업로드 → GitHub Actions 에서 실행 (로컬 실행도 가능).

  python trend_auto.py --xlsx trend_inputs/weekly/261106.xlsx [--base 2026-11-06] [--no-publish]

흐름
  1) 엑셀 로드 → 공식 데이터(ECOS 국고 3년·서울외환 15:30 종가·FRED 美 10년)와 대조
     - 중복 행으로 값이 하루씩 밀린 경우 자동 재정렬, 오기(誤記)는 공식값으로 교체, 빠진 끝부분은 공식값으로 보충
  2) 수치·기간·그래프 계산 (trend_tools/scripts/build_report.py = weekly-trend-fund-hwpx 스킬 스크립트)
  3) Gemini + 구글 검색으로 배경 조사 → 스킬 문체 규칙대로 본문(JSON) 작성
  4) HWPX 생성 → 주간 동향 분석 탭 등록(trends.html, HWPX·DOCX 다운로드)

환경변수: GEMINI_API_KEY(필수), BOK_API_KEY(국고 3년 대조용, 없으면 생략), GEMINI_TREND_MODELS(선택)
"""
import argparse
import glob
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import time
from argparse import Namespace

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
BR_PATH = os.path.join(ROOT, "trend_tools", "scripts", "build_report.py")
EXAMPLES = os.path.join(ROOT, "trend_tools", "references", "writing_examples.md")
MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_TREND_MODELS", "gemini-3.8-flash,gemini-pro-latest,gemini-flash-latest").split(",") if m.strip()]
COLS = ["USD", "US10y", "KTB3y"]
TOL = {"KTB3y": 0.0005, "USD": 0.05}          # 공식값과 '같다'고 볼 허용 오차
NAMES = {"USD": "원/달러", "US10y": "美 10년", "KTB3y": "국고 3년"}


def load_br():
    spec = importlib.util.spec_from_file_location("build_report", BR_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ 1) 데이터 대조·보정
def official(start, end):
    out = {}
    key = os.environ.get("BOK_API_KEY")
    if key:
        try:
            url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/1000/817Y002/D/"
                   f"{start:%Y%m%d}/{end:%Y%m%d}/010200000")
            rows = requests.get(url, timeout=20).json().get("StatisticSearch", {}).get("row", [])
            if rows:
                out["KTB3y"] = pd.Series({pd.Timestamp(r["TIME"]): float(r["DATA_VALUE"]) for r in rows}).sort_index()
        except Exception as e:
            print("  ECOS 조회 실패:", e)
    try:
        fx = pd.read_csv(os.path.join(ROOT, "usd_krw_3years.csv"))
        s = pd.Series(pd.to_numeric(fx["15:30 종가"], errors="coerce").values, index=pd.to_datetime(fx["날짜"])).dropna()
        out["USD"] = s[(s.index >= start) & (s.index <= end)].sort_index()
    except Exception as e:
        print("  원/달러 CSV 읽기 실패:", e)
    try:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
                         f"&cosd={start:%Y-%m-%d}&coed={end:%Y-%m-%d}", timeout=20)
        f = pd.read_csv(io.StringIO(r.text))
        out["US10y"] = pd.Series(pd.to_numeric(f.iloc[:, 1], errors="coerce").values,
                                 index=pd.to_datetime(f.iloc[:, 0])).dropna().sort_index()
    except Exception as e:
        print("  FRED 조회 실패:", e)
    return out


def diffs(df, off):
    """공식값과 다른 셀 목록 [(date, col, excel, official)] — 국고 3년·원/달러만 (美 10년은 출처별 차이가 있어 제외)."""
    res = []
    for col, tol in TOL.items():
        s = off.get(col)
        if s is None or col not in df:
            continue
        for d in df.index.intersection(s.index):
            v = df.at[d, col]
            if pd.notna(v) and abs(v - s[d]) > tol:
                res.append((d, col, float(v), float(s[d])))
    return res


def drop_dup_shift(df):
    """바로 앞 행과 세 값이 모두 같은 '중복 행'을 지우고 이후 값을 하루씩 당긴다(날짜 열은 그대로)."""
    v = df[COLS]
    same = v.diff().abs().sum(axis=1, min_count=3) == 0
    dups = list(df.index[same])
    if not dups:
        return None, []
    vals, idx = v.values.tolist(), list(df.index)
    for d in reversed(dups):
        vals.pop(idx.index(d))
        vals.append([float("nan")] * 3)
    return pd.DataFrame(vals, index=df.index, columns=COLS), dups


def fix_data(df, base, br):
    notes = []
    start = base - pd.Timedelta(days=45)
    win = df[(df.index >= start) & (df.index <= base)].copy()
    off = official(start - pd.Timedelta(days=5), base)
    got = [NAMES[k] for k in off]
    if not got:
        notes.append("공식 데이터 조회에 실패해 엑셀 값을 그대로 사용 (날짜 정렬 검증 생략)")
        return df, notes

    d0 = diffs(win, off)
    if d0:
        alt, dups = drop_dup_shift(win)
        if alt is not None:
            d1 = diffs(alt, off)
            if len(d1) < len(d0):
                win = alt
                notes.append(f"엑셀 {', '.join(f'{d.month}/{d.day}' for d in dups)} 행이 바로 앞 행과 같은 값(중복)이라 "
                             f"이후 값이 하루씩 밀려 있었음 → 중복을 지우고 값을 당겨 재정렬 "
                             f"(공식값 불일치 {len(d0)}건 → {len(d1)}건)")
        for d, col, v, o in diffs(win, off):
            win.at[d, col] = o
            notes.append(f"{d.month}/{d.day} {NAMES[col]} 엑셀 {v:,.3f} → 공식값 {o:,.3f}로 교체")

    # 끝부분(엑셀 마지막 완전한 행 이후 ~ 기준일) 공식값 보충
    filled = []
    days = sorted(set().union(*[set(s.index[(s.index > start) & (s.index <= base)]) for s in off.values()]) | set(win.index))
    win = win.reindex(pd.DatetimeIndex(days))
    last_full = win.dropna(subset=COLS).index.max()
    for d in win.index:
        if d <= last_full or not br.is_bizday(d) and d != base:
            continue
        for col in COLS:
            if pd.isna(win.at[d, col]) and col in off and d in off[col].index:
                win.at[d, col] = float(off[col][d])
                filled.append(f"{d.month}/{d.day} {NAMES[col]} {off[col][d]:,.3f}")
    # 한국 휴장일 등으로 비어 있는 행 제거, 美 10년이 아직 없는 기준일은 직전 값 유지
    win = win.dropna(subset=["USD", "KTB3y"], how="all")
    if base in win.index and pd.isna(win.at[base, "US10y"]):
        prev = win["US10y"].loc[:base].dropna()
        if len(prev):
            win.at[base, "US10y"] = prev.iloc[-1]
            notes.append(f"기준일 美 10년 값이 엑셀·FRED에 없어 직전 값({prev.iloc[-1]:.3f}%) 사용 — 확인 필요")
    if filled:
        notes.append("엑셀에 없던 값을 공식 데이터로 보충: " + ", ".join(filled)
                     + " (출처: ECOS 국고 3년, 서울외환 15:30 종가, FRED DGS10)")
    if not notes:
        notes.append(f"엑셀 날짜·값이 공식 데이터({', '.join(got)})와 일치함을 확인")
    win = win.dropna(subset=COLS)
    return pd.concat([df[df.index < start], win]).sort_index(), notes


# ------------------------------------------------------------------ 3) Gemini
def gen(prompt, search=False, json_mode=False):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    kw = {"temperature": 0.2}
    if search:
        kw["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if json_mode:
        kw["response_mime_type"] = "application/json"
    last = None
    for model in MODELS:
        for attempt in range(2):
            try:
                r = client.models.generate_content(model=model, contents=prompt,
                                                   config=types.GenerateContentConfig(**kw))
                if (r.text or "").strip():
                    return r.text, r, model
                last = "빈 응답"
            except Exception as e:
                last = e
                print(f"  Gemini {model} 실패({attempt + 1}): {e}")
                time.sleep(8)
    raise RuntimeError(f"Gemini 호출 실패: {last}")


def grounding_sources(resp):
    out = []
    try:
        for c in resp.candidates[0].grounding_metadata.grounding_chunks or []:
            if c.web and c.web.title and c.web.title not in out:
                out.append(c.web.title)
    except Exception:
        pass
    return out


RULES = """[사실 확인 규칙]
- 장중 고점과 종가를 구분. "장중 ○○%"는 기사로 장중 값임을 확인한 경우만, 종가가 반대로 움직였으면 그 사실도 반영.
- "○년 만의 최고치" 같은 기록 표현은 그 기록이 세워진 날짜를 확인. 이전 기록을 해당 주 사건과 섞지 않음.
- 매체마다 수치가 다르면 단정하지 말고 "5.3% 안팎", "5.28~5.33%"처럼 범위로.
- 지표 발표일은 미국 현지 날짜 기준. 한국 시장 반영은 다음 날일 수 있음.
- 엑셀(공식 데이터) 수치와 기사 수치가 다르면 공식 데이터를 우선.
- 확인하지 못한 세부 수치는 쓰지 않고 일반적 표현을 씀. 추측·창작 금지."""


def daily_table(df, comp, base):
    w = df.loc[comp:base]
    return "\n".join(f"  {d:%m/%d}({'월화수목금토일'[d.weekday()]}) 美10년 {r.US10y:.3f}% · 국고3년 {r.KTB3y:.3f}% · 원/달러 {r.USD:,.1f}원"
                     for d, r in w.iterrows())


def research(calc, df, prev_fx):
    comp, base = pd.Timestamp(calc["comp"]), pd.Timestamp(calc["base"])
    hint = ""
    if prev_fx:
        hint = (f"(참고: 지난주 보고서의 끝값 — 달러인덱스 {prev_fx['dxy']}, 엔/달러 {prev_fx['jpy']}. "
                "비교일 값은 이것을 이어받으므로 기준일 값만 찾으면 됨)")
    prompt = f"""당신은 국내 공공기관 기금운용실의 채권·외환 시장 애널리스트입니다. 구글 검색으로 아래 주간의 시장 변동 요인을 조사하세요.

[대상 기간] {comp:%Y-%m-%d} 종가 대비 {base:%Y-%m-%d} 종가 (조사 범위: {comp + pd.Timedelta(days=1):%Y-%m-%d} ~ {base:%Y-%m-%d})
[주간 변동 — 공식 데이터, 이 값이 기준]
- 美 국채 10년: {calc['us10y'][0]:.3f}% → {calc['us10y'][1]:.3f}% ({calc['us_chg'][0]})
- 국고채 3년: {calc['ktb3y'][0]:.3f}% → {calc['ktb3y'][1]:.3f}% ({calc['kr_chg'][0]})
- 원/달러: {calc['usd'][0]:,.1f}원 → {calc['usd'][1]:,.1f}원 ({calc['fx_chg'][0]})
[일별 종가]
{daily_table(df, comp, base)}

[조사 항목]
1. 미국금리: CPI·고용 등 지표(실제치/예상치/전월치), FOMC·연준 인사 발언, FedWatch 확률 변화, 유가, 국채 입찰, 위험자산 흐름
2. 한국금리: 외국인 국채선물 순매수/매도(계약 수), 한은 총재·금통위 발언, 국고채 발행 계획, 증시 급변
3. 원/달러 환율: 외국인 주식 순매매(금액), 달러인덱스 흐름, 수출입업체 수급, 일별 급등락 원인
4. 달러인덱스(DXY)·엔/달러 종가: {comp:%m/%d}와 {base:%m/%d} 각각 {hint}

{RULES}

[출력] 한국어로 네 구역(미국금리 / 한국금리 / 원달러 / 달러인덱스·엔달러)으로 나눠 사실을 bullet 로 정리.
각 bullet 에 날짜(현지 기준), 구체 수치, 출처(매체명·기사 날짜)를 붙이고, 확인하지 못한 항목은 '미확인'이라고 적으세요.
마지막에 '주간 변동을 가장 잘 설명하는 핵심 동인'을 구역별 한 줄로 요약하세요."""
    text, resp, model = gen(prompt, search=True)
    return text, grounding_sources(resp), model


def write_content(calc, facts, prev_fx, feedback=""):
    examples = open(EXAMPLES, encoding="utf-8").read()
    prompt = f"""기금운용실 「금융시장 주간 동향」 보고서의 본문을 작성합니다. 아래 조사 자료만 근거로 쓰세요(새 사실 추가 금지).

[주간 변동 — 확정값]
- 美 국채 10년 {calc['us_chg'][0]} ({calc['us10y'][0]:.3f}→{calc['us10y'][1]:.3f}%), 국고채 3년 {calc['kr_chg'][0]} ({calc['ktb3y'][0]:.3f}→{calc['ktb3y'][1]:.3f}%), 원/달러 {calc['fx_chg'][0]} ({calc['usd'][0]:,.1f}→{calc['usd'][1]:,.1f}원)
- 동향 기간 {calc['trend_period']}

[조사 자료]
{facts}

[문체 예시]
{examples}

[작성 규칙]
- 개조식, 명사형 종결("…영향을 받으며 주간 금리 하락", "…1,330원대에서 등락"). 각 문단 1~2문장.
- 구조: 배경/원인 → 결과. 결과의 방향은 위 확정값과 반드시 일치(△=하락, +=상승). 변동폭 "(△6.6bp)"는 쓰지 말 것(자동으로 붙음).
- 핵심 원인 구절은 kind "em"(굵게), 나머지는 "body". main 의 첫 text 는 공백 한 칸으로 시작.
- 각주 표시는 본문에 * , ** 로 넣고, notes 에 "  * …", "  ** …"(앞 공백 두 칸) 형식으로 구체 수치·날짜·출처를 넣음. 표시와 각주 개수 일치.
- 美는 "美"로 표기. 날짜는 "(10.28.)" 형식.
{RULES}
{feedback}

[출력 JSON 형식]
{{"us": {{"main": [{{"kind": "body", "text": " 美 …"}}, {{"kind": "em", "text": "…"}}], "notes": ["  * …"]}},
 "kr": {{"main": [...], "notes": [...]}},
 "fx": {{"main": [...], "notes": [...]}},
 "dxy": [비교일 종가, 기준일 종가] 또는 null, "jpy": [비교일 종가, 기준일 종가] 또는 null,
 "sources": ["매체명 - 기사 요지 (날짜)", ...],
 "checks": ["사용자가 확인해야 할 가정·기사 간 수치 차이·미확인 사항", ...]}}
{('달러인덱스·엔/달러의 비교일 값은 반드시 ' + json.dumps(prev_fx, ensure_ascii=False) + ' 의 값을 사용.') if prev_fx else ''}"""
    text, _, model = gen(prompt, json_mode=True)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text), model


TAG_RE = re.compile(r"\s*\((?:△|\+)?[\d.,]+\s*(?:bp|원)?\)\s*$|\s*\(보합\)\s*$")


def normalize(c, calc):
    """JSON 구조 검증·정리. 문제 목록을 돌려준다."""
    problems = []
    for key, chg in (("us", calc["us_chg"]), ("kr", calc["kr_chg"]), ("fx", calc["fx_chg"])):
        sec = c.get(key) or {}
        main = []
        for seg in sec.get("main") or []:
            kind, text = (seg.get("kind"), seg.get("text")) if isinstance(seg, dict) else (seg[0], seg[1])
            if text:
                main.append(["em" if kind == "em" else "body", str(text)])
        if not main:
            problems.append(f"{key}: 본문이 비어 있음")
            continue
        main[-1][1] = TAG_RE.sub("", main[-1][1])
        if not main[0][1].startswith(" "):
            main[0][1] = " " + main[0][1]
        notes = []
        for n in sec.get("notes") or []:
            n = str(n).strip()
            if n:
                notes.append("  " + n)
        body = "".join(t for _, t in main)
        tail = body[-25:]
        if key != "fx" or ("상승" in tail or "하락" in tail):
            want = {"up": "상승", "down": "하락"}.get(chg[1])
            other = {"up": "하락", "down": "상승"}.get(chg[1])
            if want and want not in tail and other in tail:
                problems.append(f"{key}: 결과 방향이 실제 변동({chg[0]})과 반대")
        marks = len(re.findall(r"(?<!\*)\*(?!\*)", body)) + len(re.findall(r"\*\*", body))
        if marks != len(notes):
            problems.append(f"{key}: 각주 표시 {marks}개와 각주 {len(notes)}개가 다름")
        c[key] = {"main": main, "notes": notes}
    for k in ("dxy", "jpy"):
        v = c.get(k)
        try:
            c[k] = [round(float(v[0]), 1), round(float(v[1]), 1)] if v else None
        except Exception:
            c[k] = None
    return problems


def prev_report_fx(comp):
    for mp in glob.glob(os.path.join(ROOT, "trend_reports", "weekly", "*", "meta.json")):
        m = json.load(open(mp, encoding="utf-8"))
        if (m.get("calc") or {}).get("base") == comp:
            t = m.get("content") or {}
            if t.get("dxy") and t.get("jpy"):
                return {"dxy": t["dxy"][1], "jpy": t["jpy"][1], "from": m["id"]}
    return None


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True, nargs="+")
    ap.add_argument("--base", help="기준일 YYYY-MM-DD (없으면 파일명 YYMMDD → 엑셀 마지막 날짜)")
    ap.add_argument("--no-publish", action="store_true", help="탭 등록 없이 HWPX 만 생성")
    ap.add_argument("--work", help="작업 폴더 (기본: 임시 폴더)")
    a = ap.parse_args()
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("GEMINI_API_KEY 가 없습니다 (GitHub Secrets 또는 .env).")

    br = load_br()
    df = br.load_data(a.xlsx)
    if a.base:
        base = pd.Timestamp(a.base)
    else:
        m = re.search(r"(\d{6})", os.path.basename(a.xlsx[0]))
        base = pd.Timestamp(f"20{m.group(1)[:2]}-{m.group(1)[2:4]}-{m.group(1)[4:]}") if m else df.index.max()
    print(f"[1/4] 데이터 확인 — 기준일 {base.date()}, 엑셀 {df.index.min().date()}~{df.index.max().date()}")
    df, data_notes = fix_data(df, base, br)
    for n in data_notes:
        print("  ·", n)
    if base not in df.index:
        sys.exit(f"기준일 {base.date()} 데이터가 엑셀·공식 데이터 모두에 없습니다.")

    work = a.work or tempfile.mkdtemp(prefix="trend_")
    os.makedirs(work, exist_ok=True)
    fixed = os.path.join(work, "data_fixed.xlsx")
    df.rename(columns={"USD": "환율", "US10y": "미국10y", "KTB3y": "한국3y"}).rename_axis("일자").reset_index().to_excel(fixed, index=False)
    print("[2/4] 수치·그래프 계산")
    br.cmd_calc(Namespace(xlsx=[fixed], base=str(base.date()), comp=None, work=work))
    calc = json.load(open(os.path.join(work, "calc.json"), encoding="utf-8"))
    if calc["comp_was_shifted"]:
        data_notes.append(f"비교일 {calc['comp_target']} 데이터가 없어 직전 데이터일 {calc['comp']} 사용")

    print("[3/4] Gemini 조사·작성")
    prev_fx = prev_report_fx(calc["comp"])
    facts, gsrc, rmodel = research(calc, df, prev_fx)
    content, wmodel = write_content(calc, facts, prev_fx)
    problems = normalize(content, calc)
    if problems:
        print("  재작성:", problems)
        content, wmodel = write_content(calc, facts, prev_fx, "[이전 작성본의 문제 — 반드시 고칠 것]\n- " + "\n- ".join(problems))
        problems = normalize(content, calc)
    if prev_fx:
        for k in ("dxy", "jpy"):
            if content.get(k):
                content[k][0] = prev_fx[k]
        data_notes.append(f"달러인덱스·엔/달러 시작값은 지난주 보고서({prev_fx['from']}) 끝값을 이어받음")
    else:
        data_notes.append("달러인덱스·엔/달러 값은 AI가 기사에서 찾은 종가 — 확인 필요")
    data_notes += [f"[AI 확인 요청] {x}" for x in (content.pop("checks", None) or [])]
    data_notes += [f"[자동 검사] {x}" for x in problems]
    data_notes.append(f"본문은 Gemini({rmodel} 조사 / {wmodel} 작성)가 구글 검색 자료로 작성한 초안 — 사용 전 사실관계 확인 필요")
    sources = list(dict.fromkeys((content.pop("sources", None) or []) + [f"검색 출처: {s}" for s in gsrc]))
    cpath, npath = os.path.join(work, "content.json"), os.path.join(work, "notes.json")
    json.dump(content, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"data_notes": data_notes, "sources": sources, "research": facts},
              open(npath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("[4/4] HWPX 생성·게시")
    out = os.path.join(work, "out")
    br.cmd_build(Namespace(work=work, content=cpath, out=out))
    hwpx = os.path.join(out, calc["filename"])
    if a.no_publish:
        print("생성:", hwpx)
        return
    import dashboard_trends
    os.chdir(ROOT)
    dashboard_trends.cmd_add(Namespace(type="weekly", id=base.strftime("%y%m%d"), hwpx=hwpx, calc=os.path.join(work, "calc.json"),
                                       content=cpath, images=work, notes=npath))


if __name__ == "__main__":
    main()
