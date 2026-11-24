#!/usr/bin/env python3
"""금융시장 주간 동향 HWPX 생성 도구.

사용법
  1) 수치·기간 계산 + 그래프 생성
     python build_report.py calc --base 2026-10-15 --xlsx <엑셀 파일들> --work /home/claude/wt
     → <work>/calc.json, <work>/image1~3.bmp 생성, 요약을 stdout에 출력

  2) 본문 JSON을 작성한 뒤 HWPX 생성
     python build_report.py build --work /home/claude/wt --content /home/claude/wt/content.json \
         --out /mnt/user-data/outputs

양식은 이 스킬의 assets/template_261008.hwpx 를 항상 사용한다 (사용자 업로드 불필요).
"""
import argparse, datetime as dt, html, json, os, re, sys, zipfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, 'assets', 'template_261008.hwpx')

# 한국 채권시장 휴장일 (운용계획 시작일 계산용). 연도가 넘어가면 웹 검색으로 확인 후 보완.
KR_HOLIDAYS = {
    '2026-01-01', '2026-02-16', '2026-02-17', '2026-02-18', '2026-03-02', '2026-05-01',
    '2026-05-05', '2026-05-25', '2026-06-03', '2026-08-17', '2026-09-24', '2026-09-25',
    '2026-10-05', '2026-10-09', '2026-12-25', '2026-12-31',
    '2027-01-01', '2027-02-08', '2027-02-09', '2027-03-01', '2027-05-05', '2027-05-13',
    '2027-08-16', '2027-09-14', '2027-09-15', '2027-09-16', '2027-10-04', '2027-10-11',
    '2027-12-27', '2027-12-31',
}

# ---------------------------------------------------------------- data loading
def load_data(paths):
    import pandas as pd
    frames = []
    for p in paths:
        raw = pd.read_excel(p, header=None)
        # (a) 주간동향_그래프.xlsx : 헤더 '일자','환율','미국10y','한국3y'
        hdr_row = None
        for i in range(min(10, len(raw))):
            vals = [str(v).strip() for v in raw.iloc[i].tolist()]
            if '일자' in vals:
                hdr_row = i
                break
        if hdr_row is not None:
            df = pd.read_excel(p, header=hdr_row)
            df.columns = [str(c).strip() for c in df.columns]
            ren = {}
            for c in df.columns:
                lc = c.lower()
                if c == '일자': ren[c] = 'date'
                elif '환율' in c or 'usd' in lc: ren[c] = 'USD'
                elif '미국' in c or 'us10' in lc: ren[c] = 'US10y'
                elif ('한국' in c or 'ktb' in lc) and '3' in c: ren[c] = 'KTB3y'
            df = df.rename(columns=ren)[[v for v in ['date', 'USD', 'US10y', 'KTB3y'] if v in ren.values()]]
        else:
            # (b) 기존 2개 파일 형식: 7행부터 데이터
            name = os.path.basename(p)
            df = raw.iloc[7:].copy()
            if '환율' in name:
                df = df.iloc[:, :4]; df.columns = ['date', 'USD', 'JPY100', 'CNY']; df = df[['date', 'USD']]
            else:
                df = df.iloc[:, :4]; df.columns = ['date', 'KTB3y', 'KTB10y', 'US10y']; df = df[['date', 'KTB3y', 'US10y']]
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).set_index('date')
        frames.append(df.apply(pd.to_numeric, errors='coerce'))
    out = frames[0]
    for f in frames[1:]:
        out = out.combine_first(f)
    out = out.sort_index()
    out = out[~out.index.duplicated()]
    missing = {'USD', 'US10y', 'KTB3y'} - set(out.columns)
    if missing:
        sys.exit(f'엑셀에서 다음 열을 찾지 못했습니다: {missing}')
    return out.dropna(subset=['USD', 'US10y', 'KTB3y'], how='all')


def md(d):
    return f'{d.month}.{d.day}.'


def is_bizday(d):
    return d.weekday() < 5 and d.strftime('%Y-%m-%d') not in KR_HOLIDAYS


def signed(v, unit, nd=1):
    """증가 '+4.2원', 감소 '△9.4bp', 0 이면 '보합'."""
    r = round(v, nd)
    if r == 0:
        return '보합', 'flat'
    return (f'+{abs(r):,.{nd}f}{unit}', 'up') if r > 0 else (f'△{abs(r):,.{nd}f}{unit}', 'down')


# ---------------------------------------------------------------- calc
def cmd_calc(a):
    import pandas as pd
    df = load_data(a.xlsx)
    base = pd.Timestamp(a.base)
    if base not in df.index:
        sys.exit(f'기준일 {a.base} 데이터가 엑셀에 없습니다. 마지막 데이터일: {df.index.max().date()}')
    target = base - pd.Timedelta(days=7)
    if a.comp:
        comp = pd.Timestamp(a.comp)
    else:
        prior = df.index[df.index <= target]
        if len(prior) == 0:
            sys.exit('비교일 데이터가 없습니다.')
        comp = prior.max()
    b, c = df.loc[base], df.loc[comp]
    us = (b.US10y - c.US10y) * 100
    kr = (b.KTB3y - c.KTB3y) * 100
    fx = b.USD - c.USD

    monday = base - pd.Timedelta(days=base.weekday())
    wk = df.index[(df.index >= monday) & (df.index <= base)]
    trend_start = wk.min() if len(wk) else monday
    d = base + pd.Timedelta(days=1)
    while not is_bizday(d):
        d += pd.Timedelta(days=1)
    plan_start = d
    plan_end = (base - pd.Timedelta(days=base.weekday())) + pd.Timedelta(days=11)  # 다음 주 금요일
    if plan_end < plan_start:
        plan_end = plan_start + pd.Timedelta(days=(4 - plan_start.weekday()) % 7)

    res = {
        'base': str(base.date()), 'comp': str(comp.date()), 'comp_target': str(target.date()),
        'comp_was_shifted': bool(comp != target),
        'us10y': [round(float(c.US10y), 3), round(float(b.US10y), 3)],
        'ktb3y': [round(float(c.KTB3y), 3), round(float(b.KTB3y), 3)],
        'usd': [round(float(c.USD), 1), round(float(b.USD), 1)],
        'us_chg': signed(us, 'bp'), 'kr_chg': signed(kr, 'bp'), 'fx_chg': signed(fx, '원'),
        'trend_period': f'{md(trend_start)}~{md(base)}', 'plan_period': f'{md(plan_start)}~{md(plan_end)}',
        'title': f'금융시장 주간 동향 [{md(trend_start)}~{md(base)}] 및 운용 계획 [{md(plan_start)}~{md(plan_end)}]',
        'filename': base.strftime('%y%m%d') + '_금융시장_주간_동향_및_운용계획.hwpx',
    }
    os.makedirs(a.work, exist_ok=True)
    make_charts(df, base, comp, a.work)
    json.dump(res, open(os.path.join(a.work, 'calc.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


def make_charts(df, base, comp, work):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    win = df.loc[:base].tail(14)
    labels = [f'{d.month}/{d.day}' for d in win.index]
    k = list(win.index).index(comp) if comp in win.index else 0
    with zipfile.ZipFile(TEMPLATE) as z:
        sizes = {n: Image.open(z.open(f'BinData/{n}.bmp')).size for n in ('image1', 'image2', 'image3')}
    specs = [('US10y', '{:.3f}', 0.1, 'image1'), ('KTB3y', '{:.3f}', 0.1, 'image2'), ('USD', '{:,.1f}', 10, 'image3')]
    for col, fmt, step, name in specs:
        y = win[col].values.astype(float); x = np.arange(len(y)); w, h = sizes[name]
        lo = np.floor(y.min() / step) * step - step; hi = np.ceil(y.max() / step) * step + step
        while (hi - lo) / step > 6: step *= 2; lo = np.floor(y.min() / step) * step; hi = np.ceil(y.max() / step) * step
        fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=100)
        ax.plot(x[:k + 1], y[:k + 1], color='#5B9BD5', lw=2.2)
        ax.plot(x[k:], y[k:], color='#ED7D31', lw=2.2)
        ticks = np.arange(lo, hi + step / 2, step)
        ax.set_ylim(lo, hi); ax.set_yticks(ticks); ax.set_yticklabels([fmt.format(t) for t in ticks])
        ax.yaxis.tick_right(); ax.tick_params(length=0, labelsize=7.5, colors='#595959')
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=6.3, color='#595959'); ax.set_xlim(-0.5, len(y) - 0.5)
        ax.grid(axis='y', color='#D9D9D9', lw=0.8)
        for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
        ax.spines['bottom'].set_color('#BFBFBF')
        for i in sorted({0, k, len(y) - 1}):
            nb = [y[j] for j in (i - 1, i + 1) if 0 <= j < len(y)]
            up = y[i] >= np.mean(nb)
            ax.annotate(fmt.format(y[i]), (i, y[i]), xytext=(0, 9 if up else -13), textcoords='offset points',
                        ha='right' if i == len(y) - 1 else ('left' if i == 0 else 'center'), fontsize=8.5)
        plt.subplots_adjust(left=0.03, right=0.88, top=0.95, bottom=0.1)
        png = os.path.join(work, name + '.png'); fig.savefig(png, dpi=100, facecolor='white'); plt.close(fig)
        Image.open(png).convert('RGB').resize((w, h)).save(os.path.join(work, name + '.bmp'))


# ---------------------------------------------------------------- build
# template_261008.hwpx 의 charPr / paraPr ID (build 시 색상·굵기 검증)
STY = {
    'us': dict(pp='17', bullet='5', head=[('34', '(미국금리'), ('35', ')')], body='36', em='41'),
    'kr': dict(pp='17', bullet='5', head=[('43', '(한국금리)')], body='36', em='41'),
    'fx': dict(pp='19', bullet='36', head=[('48', '(원/달러 환율)')], body='49', em='50'),
}
NOTE_PP, NOTE_RUN, SUMMARY_PP = '18', '28', '21'
UP, DOWN = '39', '38'          # 1100 빨강 굵게 / 1100 파랑 굵게
DOWN_FX = '47'                 # 원/달러 문단용 파랑 굵게
SPACERS = {'us_main': ('18', '52'), 'us_notes': ('17', '45'), 'kr_main': ('17', '51'),
           'kr_notes': ('17', '44'), 'fx_main': ('19', '37')}


def check_styles(hdr):
    def prop(cid):
        m = re.search(rf'<hh:charPr id="{cid}"([^>]*)>(.*?)</hh:charPr>', hdr, re.DOTALL)
        return re.search(r'textColor="([^"]+)"', m.group(1)).group(1), '<hh:bold/>' in m.group(2)
    for cid, want in ((UP, ('#FF0000', True)), (DOWN, ('#0000FF', True)), (DOWN_FX, ('#0000FF', True))):
        got = prop(cid)
        if got != want:
            sys.exit(f'템플릿 charPr {cid} 이 예상과 다릅니다: {got} (기대 {want})')


def run(c, t):
    return f'<hp:run charPrIDRef="{c}"><hp:t>{html.escape(t, quote=False)}</hp:t></hp:run>'


def para(pp, runs):
    return f'<hp:p id="2147483648" paraPrIDRef="{pp}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">{"".join(runs)}</hp:p>'


def spacer(key):
    pp, c = SPACERS[key]
    return f'<hp:p id="2147483648" paraPrIDRef="{pp}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="{c}"/></hp:p>'


def tag_run(chg, fx=False):
    txt, d = chg
    c = UP if d == 'up' else (DOWN_FX if fx else DOWN) if d == 'down' else NOTE_RUN
    return run(c, f'({txt})')


def main_para(key, segs, chg):
    s = STY[key]
    runs = [run(s['bullet'], '▪')] + [run(c, t) for c, t in s['head']]
    for kind, text in segs:
        runs.append(run(s['em'] if kind == 'em' else s['body'], text))
    runs.append(run(s['body'], ' '))
    runs.append(tag_run(chg, fx=(key == 'fx')))
    return para(s['pp'], runs)


def note_para(text):
    return para(NOTE_PP, [run(NOTE_RUN, text)])


def summary_para(calc, dxy, jpy):
    def colored(v, unit, nd):
        txt, d = signed(v, unit, nd)
        return run(UP if d == 'up' else DOWN if d == 'down' else NOTE_RUN, txt)
    u0, u1 = calc['usd']
    runs = [run(NOTE_RUN, f'   ※ 원/달러 환율 : {u0:,.1f}원 → {u1:,.1f}원('), colored(u1 - u0, '원', 1)]
    for name, pair in (('달러인덱스', dxy), ('엔/달러 환율', jpy)):
        if pair:
            a, b = pair
            runs += [run(NOTE_RUN, f'), {name} : {a:.1f} → {b:.1f}('), colored(b - a, '', 1)]
    runs.append(run(NOTE_RUN, ')'))
    return para(SUMMARY_PP, runs)


def cmd_build(a):
    calc = json.load(open(os.path.join(a.work, 'calc.json'), encoding='utf-8'))
    content = json.load(open(a.content, encoding='utf-8'))
    with zipfile.ZipFile(TEMPLATE) as z:
        xml = z.read('Contents/section0.xml').decode('utf-8')
        hdr = z.read('Contents/header.xml').decode('utf-8')
    check_styles(hdr)

    body = [main_para('us', content['us']['main'], calc['us_chg']), spacer('us_main')]
    body += [note_para(t) for t in content['us'].get('notes', [])] + [spacer('us_notes')]
    body += [main_para('kr', content['kr']['main'], calc['kr_chg']), spacer('kr_main')]
    body += [note_para(t) for t in content['kr'].get('notes', [])] + [spacer('kr_notes')]
    body += [main_para('fx', content['fx']['main'], calc['fx_chg']), spacer('fx_main')]
    body += [note_para(t) for t in content['fx'].get('notes', [])]
    body += [summary_para(calc, content.get('dxy'), content.get('jpy'))]

    tcs = list(re.finditer(r'<hp:tc[^>]*>.*?</hp:tc>', xml, re.DOTALL))
    target = [m for m in tcs if '(미국금리' in m.group(0) and '<hp:tc' not in m.group(0)[5:]]
    if len(target) != 1:
        sys.exit('본문 셀(▪미국금리)을 찾지 못했습니다.')
    old = target[0].group(0)
    sl = re.search(r'(<hp:subList[^>]*>)(.*?)(</hp:subList>)', old, re.DOTALL)
    xml = xml.replace(old, old.replace(sl.group(0), sl.group(1) + ''.join(body) + sl.group(3), 1), 1)

    t_old = re.search(r'금융시장 주간 동향[^<]*', xml).group(0)
    xml = xml.replace(t_old, calc['title'], 1)

    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, calc['filename'])
    with zipfile.ZipFile(TEMPLATE) as zin, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            f = it.filename
            if f == 'Contents/section0.xml':
                data = xml.encode('utf-8')
            elif f == 'version.xml':
                # 템플릿은 구버전(9.x, 변환기 생성) 표기 → 한글 2018 이상에서 색상을 구형 방식으로 해석해
                # 'none' 배경이 검은색, 빨강/파랑이 뒤바뀌어 보임. 한글 2018 저장본(example_260515)과 동일하게 맞춤.
                data = re.sub(r'appVersion="[^"]*"', 'appVersion="10, 0, 0, 14727 WIN32LEWindows_8"',
                              zin.read(f).decode('utf-8')).encode('utf-8')
            elif f.startswith('BinData/image') and os.path.exists(os.path.join(a.work, os.path.basename(f))):
                data = open(os.path.join(a.work, os.path.basename(f)), 'rb').read()
            else:
                data = zin.read(f)
            zout.writestr(it, data, compress_type=zipfile.ZIP_STORED if f in ('mimetype', 'version.xml') else zipfile.ZIP_DEFLATED)
        # container.xml 이 참조하는 미리보기 텍스트(템플릿에 누락) 추가
        if 'Preview/PrvText.txt' not in zin.namelist():
            prv = html.unescape(''.join(f'<{t}>' for t in re.findall(r'<hp:t>(.*?)</hp:t>', xml)))
            zout.writestr('Preview/PrvText.txt', prv[:1024].encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)
    # 검증
    from xml.dom import minidom
    with zipfile.ZipFile(out) as z:
        assert z.namelist()[0] == 'mimetype'
        minidom.parseString(z.read('Contents/section0.xml'))
        text = ''.join(re.findall(r'<hp:t>(.*?)</hp:t>', z.read('Contents/section0.xml').decode('utf-8')))
    print('생성 완료:', out)
    print(html.unescape(text[text.find('금융시장 주간'):text.find('금융시장 주간') + 70]))
    print(html.unescape(text[text.find('▪'):text.find('차주계획')]))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('calc'); c.add_argument('--base', required=True); c.add_argument('--xlsx', nargs='+', required=True)
    c.add_argument('--work', required=True); c.add_argument('--comp', help='비교일 직접 지정 (YYYY-MM-DD)')
    b = sp.add_parser('build'); b.add_argument('--work', required=True); b.add_argument('--content', required=True)
    b.add_argument('--out', required=True)
    a = p.parse_args()
    cmd_calc(a) if a.cmd == 'calc' else cmd_build(a)
