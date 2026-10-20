/* 위탁운용 운용분석보고서 화면 렌더링 (데이터: window.REPORT_DATA, 생성: dashboard_report.py) */
(function () {
  'use strict';
  const D = window.REPORT_DATA;
  const META = D.meta;
  const DD = D.daily;
  const DI = {};
  DD.dates.forEach((d, i) => { DI[d] = i; });
  const $ = (s) => document.querySelector(s);

  // ---------- 포맷 ----------
  const isNum = (v) => v !== null && v !== undefined && !isNaN(v);
  const nf = (v, d = 2) => isNum(v) ? Number(v).toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d }) : '-';
  const sg = (v, d = 1) => isNum(v) ? (v > 0 ? '+' : '') + nf(v, d) : '-';
  const cl = (v) => !isNum(v) ? '' : (v > 0 ? 'pos' : (v < 0 ? 'neg' : ''));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const md = (s) => { const p = s.split('-'); return `${+p[1]}/${+p[2]}`; };
  const N = (v, d) => `<td>${nf(v, d)}</td>`;              // 숫자
  const S = (v, d) => `<td class="${cl(v)}">${sg(v, d)}</td>`; // 부호·색상
  const L = (h) => `<td class="l">${h}</td>`;
  const TH = (cols) => '<thead><tr>' + cols.map((c) => c.startsWith('<') ? c : `<th>${c}</th>`).join('') + '</tr></thead>';
  const THL = (c) => `<th class="l">${c}</th>`;
  const table = (head, rows) => `<div class="tw"><table>${TH(head)}<tbody>${rows.join('')}</tbody></table></div>`;
  const fname = (f) => esc(f.n) + (f.st === '신규' ? '<span class="tag new">신규</span>' : '') + (f.st === '해지' ? '<span class="tag end">해지</span>' : '');
  const empty = (t) => `<p class="empty">${t}</p>`;
  const COLORS = ['#4f46e5', '#0ea5e9', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#64748b', '#84cc16'];

  // ---------- 차트 공통 ----------
  let charts = [];
  if (window.Chart) {
    Chart.defaults.font.family = "'Inter','Malgun Gothic',sans-serif";
    Chart.defaults.color = '#64748b';
    Chart.defaults.animation = false;
    Chart.defaults.maintainAspectRatio = false;
    // 보고 기간 음영 표시
    Chart.register({
      id: 'band',
      beforeDatasetsDraw(ch, args, opts) {
        if (!opts || opts.from == null) return;
        const x = ch.scales.x, a = ch.chartArea;
        const x0 = x.getPixelForValue(opts.from), x1 = x.getPixelForValue(opts.to);
        const c = ch.ctx;
        c.save();
        c.fillStyle = 'rgba(79,70,229,.08)';
        c.fillRect(Math.min(x0, x1), a.top, Math.max(2, Math.abs(x1 - x0)), a.bottom - a.top);
        c.restore();
      }
    });
  }
  function mkChart(id, cfg) {
    const el = document.getElementById(id);
    if (el && window.Chart) charts.push(new Chart(el, cfg));
  }
  function lineCfg(labels, datasets, title, band, yfmt, y2) {
    const scales = { x: { ticks: { maxTicksLimit: 8, autoSkip: true } }, y: { ticks: { callback: yfmt || ((v) => v) } } };
    if (y2) scales.y2 = { position: 'right', grid: { drawOnChartArea: false }, ticks: { callback: y2 } };
    return {
      type: 'line',
      data: { labels, datasets: datasets.map((d, i) => Object.assign({ borderColor: COLORS[i % COLORS.length], backgroundColor: COLORS[i % COLORS.length], pointRadius: 0, borderWidth: 1.7, tension: 0.2, spanGaps: true }, d)) },
      options: { interaction: { mode: 'index', intersect: false }, plugins: { title: { display: true, text: title }, legend: { labels: { boxWidth: 12 } }, band: band || {} }, scales }
    };
  }
  function windowIdx(p) {
    const e = DI[p.e];
    const s = state.kind === 'W' ? Math.max(0, e - 91) : 0;
    return [s, e];
  }
  function bandOpt(p, s) { return { from: Math.max(0, DI[p.b] - s), to: DI[p.e] - s }; }
  const sliceLabels = (s, e) => DD.dates.slice(s, e + 1).map(md);

  // ---------- 상태 ----------
  const state = { kind: 'W', idx: 0 };
  const firstComplete = (k) => Math.max(0, D.periods[k].findIndex((p) => !p.partial));

  // ---------- 섹션 ----------
  function sSummary(p) {
    const g = p.groups, gu = g.U, go = g.O, tr = p.tr, mv = p.mkt.vals;
    const tot = ['U', 'D', 'O'].reduce((a, k) => a + ((g[k] || {}).aum || 0), 0);
    const flow = ['U', 'D', 'O'].reduce((a, k) => a + ((g[k] || {}).flow || 0), 0);
    const k = [];
    if (gu) {
      k.push(['국내 유니버스 기간 수익률', `${nf(gu.r, 3)}<small>%</small>`, `BM ${nf(gu.rb, 3)}% · 초과 ${sg(gu.ex)}bp`]);
      k.push(['BM 상회 펀드', `${gu.nout}<small>/ ${gu.nbm}개</small>`, `연초 이후 가중 초과 ${sg(gu.ytdx)}bp`]);
    }
    k.push(['위탁 순자산 (기말)', `${nf(tot / 10000, 2)}<small>조원</small>`, `기간 순유출입 ${sg(flow, 0)}억`]);
    if (tr && !tr.empty) k.push(['실현 매매손익', `${sg(tr.pnl, 1)}<small>억원</small>`, `매입 ${nf(tr.buy, 0)}억 / 매도 ${nf(tr.sell, 0)}억`]);
    if (mv.ktb3) k.push(['국고 3년', `${nf(mv.ktb3[1], 3)}<small>%</small>`, `${sg((mv.ktb3[1] - mv.ktb3[0]) * 100)}bp` + (mv.ktb10 ? ` · 10년 ${nf(mv.ktb10[1], 3)}% (${sg((mv.ktb10[1] - mv.ktb10[0]) * 100)}bp)` : '')]);
    if (go) k.push(['해외채권형 기간 수익률', `${nf(go.r, 2)}<small>%</small>`, `BM 대비 ${sg(go.ex)}bp` + (mv.usdkrw ? ` · 원/달러 ${sg((mv.usdkrw[1] / mv.usdkrw[0] - 1) * 100, 2)}%` : '')]);
    const kp = '<div class="kpis">' + k.map((x) => `<div class="kpi"><div class="kl">${x[0]}</div><div class="kv">${x[1]}</div><div class="ks">${x[2]}</div></div>`).join('') + '</div>';
    const top = p.cm.slice(0, 4).map((c) => `<li>${c}</li>`).join('');
    return kp + `<h3>핵심 요약</h3><ul class="pts">${top}</ul>` + (p.partial ? '<p class="note">※ 진행 중인 기간으로, 데이터 최종일까지의 수치입니다.</p>' : '');
  }

  function sMarket(p) {
    const rows = p.mkt.rows.map((r) => {
      const isW = r.u === '원';
      return `<tr>${L(r.lab)}<td>${nf(r.s, isW ? 1 : 3)}${isW ? '' : '%'}</td><td>${nf(r.e, isW ? 1 : 3)}${isW ? '' : '%'}</td><td class="${cl(r.ch)}">${sg(r.ch, isW ? 2 : 1)}${isW ? '%' : 'bp'}</td></tr>`;
    });
    const sp = Object.entries(p.mkt.sp).map(([k, v]) => `<tr>${L(k)}<td>${nf(v.s, 1)}</td><td>${nf(v.e, 1)}</td>${S(v.ch, 1)}</tr>`);
    let h = '<div class="grid2"><div>' + table([THL('지표'), `기초 (${md(p.b)})`, `기말 (${md(p.e)})`, '변화'], rows) + '</div><div>'
      + table([THL('스프레드 (bp)'), '기초', '기말', '변화'], sp) + '<p class="note">※ 시장금리는 해당 일자 이전 최근 영업일 종가 기준(한국은행 ECOS, FRED). 원/달러는 서울 15:30 종가.</p></div></div>';
    h += '<div class="grid2"><div class="chart"><canvas id="cMkt1"></canvas></div><div class="chart"><canvas id="cMkt2"></canvas></div></div>';
    return h;
  }

  function uFunds(p) { return p.funds.filter((f) => f.g === 'U'); }

  function sPerf(p) {
    const U = uFunds(p);
    if (!U.length) return empty('해당 기간 국내 유니버스 펀드 데이터가 없습니다.');
    const rank = U.filter((f) => isNum(f.ex)).slice().sort((a, b) => b.ex - a.ex).map((f) => f.c);
    const rows = U.map((f) => `<tr>${L(esc(f.m))}${L(fname(f))}${N(f.aumL, 0)}${N(f.r, 3)}${N(f.rb, 3)}${S(f.ex, 1)}${N(f.ytd, 3)}${N(f.ytdb, 3)}${S(f.ytdx, 1)}<td>${rank.indexOf(f.c) + 1 || '-'}</td></tr>`);
    const g = p.groups.U;
    rows.push(`<tr class="sum">${L('합계/가중평균')}${L(`${g.n}개`)}${N(g.aum, 0)}${N(g.r, 3)}${N(g.rb, 3)}${S(g.ex, 1)}<td>-</td><td>-</td>${S(g.ytdx, 1)}<td></td></tr>`);
    return table([THL('운용사'), THL('펀드'), '순자산(억)', '기간 수익률(%)', 'BM(%)', '초과(bp)', '연초이후(%)', 'BM(%)', '초과(bp)', '순위'], rows)
      + '<div class="chart"><canvas id="cEx"></canvas></div>'
      + '<p class="note">※ 수익률은 기준가(보수 차감 후) 기준, BM은 펀드별 BM지수 기준. 가중평균은 기간 평균순자산 가중. 신규 펀드는 설정일 이후, 해지 펀드는 최종일까지. 운용사명은 펀드 코드쌍(1·2호, 3·4호 …) 기준 표기.</p>';
  }

  function sAttr(p) {
    const U = uFunds(p).filter((f) => f.at);
    if (!U.length) return empty('요인분해에 필요한 BM 듀레이션·YTM 정보가 없습니다.');
    const rows = U.map((f) => `<tr>${L(fname(f))}${S(f.ex, 1)}${S(f.at.carry, 1)}${S(f.at.dur, 1)}${S(f.at.res, 1)}${S(f.at.gapD, 2)}${S(f.at.gapY, 0)}${S(f.at.dy, 1)}</tr>`);
    return table([THL('펀드'), '초과(bp)', '캐리 효과', '듀레이션 효과', '기타(커브·종목·매매)', '평균 듀레이션 갭(년)', '평균 YTM 갭(bp)', 'BM YTM 변화(bp)'], rows)
      + '<div class="chart tall"><canvas id="cAtt"></canvas></div>'
      + '<p class="note">※ 추정치입니다. 캐리 효과 = 기간 평균(펀드 YTM − BM YTM) × 경과일/365, 듀레이션 효과 = −기간 평균(펀드 듀레이션 − BM 듀레이션) × BM YTM 변화, 기타 = 초과수익 − 캐리 − 듀레이션 (커브 포지션·섹터·종목 선택·매매 효과 및 근사 오차 포함).</p>';
  }

  function sMgr(p) {
    if (!p.mgr || !p.mgr.length) return empty('운용사별 비교 대상이 없습니다.');
    const ms = p.mgr.slice().sort((a, b) => (isNum(b.ex) ? b.ex : -1e9) - (isNum(a.ex) ? a.ex : -1e9));
    const rows = ms.map((m, i) => `<tr><td>${i + 1}</td>${L(esc(m.m))}${L(esc(m.funds))}${N(m.aum, 0)}${N(m.r, 3)}${S(m.ex, 1)}${S(m.ytdx, 1)}${S(m.dg, 2)}${S(m.pnl, 1)}${N(m.to, 1)}</tr>`);
    return table(['순위', THL('운용사'), THL('펀드'), '순자산(억)', '기간 수익률(%)', '기간 초과(bp)', '연초이후 초과(bp)', '듀레이션 갭(년)', '실현손익(억)', '회전율(%)'], rows)
      + '<p class="note">※ 운용사 단위 수치는 소속 펀드의 평균순자산 가중평균. 회전율 = (매입+매도)/2 ÷ 평균순자산.</p>';
  }

  function sPos(p) {
    const F = p.funds.filter((f) => f.g !== 'O');
    const rows = F.map((f) => `<tr>${L(fname(f))}${N(f.d, 2)}${N(f.db, 2)}${S(f.dg, 2)}${S(f.dd, 2)}${N(f.y, 2)}${N(f.yb, 2)}${S(f.yg, 0)}${N(f.wam, 2)}${N(f.wb, 1)}${N(f.ws, 1)}</tr>`);
    return table([THL('펀드'), '듀레이션', 'BM 듀레이션', '갭(년)', '기간 변화', 'YTM(%)', 'BM YTM(%)', 'YTM 갭(bp)', '가중잔존만기(년)', '채권(%)', '단기(%)'], rows)
      + '<div class="grid2"><div class="chart"><canvas id="cDgB"></canvas></div><div class="chart"><canvas id="cDgL"></canvas></div></div>'
      + '<p class="note">※ 기말 기준. 듀레이션은 펀드 전체(All) 기준, 갭 = 펀드 − BM. 차트 음영은 보고 기간.</p>';
  }

  function sFlow(p) {
    const groups = [['U', '국내채권형 유니버스'], ['D', '일임 채권형'], ['O', '해외채권형']];
    const rows = [];
    let t0 = 0, tf = 0, tg = 0, t1 = 0;
    groups.forEach(([g, name]) => {
      const F = p.funds.filter((f) => f.g === g);
      if (!F.length) return;
      rows.push(`<tr class="grp"><td colspan="6">${name}</td></tr>`);
      F.forEach((f) => rows.push(`<tr>${L(fname(f))}${N(f.aum0, 0)}${S(f.flow, 0)}${S(f.gain, 1)}${N(f.aum, 0)}${L(f.st === '해지' ? `해지 (${md(f.last)})` : (f.st === '신규' ? `설정 (${md(f.first)})` : ''))}</tr>`));
      const gs = p.groups[g];
      rows.push(`<tr class="sum">${L('소계')}${N(gs.aum0, 0)}${S(gs.flow, 0)}${S(gs.gain, 1)}${N(gs.aum, 0)}<td></td></tr>`);
      t0 += gs.aum0 || 0; tf += gs.flow || 0; tg += gs.gain || 0; t1 += gs.aum || 0;
    });
    rows.push(`<tr class="sum">${L('합계')}${N(t0, 0)}${S(tf, 0)}${S(tg, 1)}${N(t1, 0)}<td></td></tr>`);
    let h = table([THL('펀드'), '기초 순자산(억)', '순유출입(억)', '운용손익 추정(억)', '기말 순자산(억)', THL('비고')], rows);
    const xf = p.tr && p.tr.xfer;
    if (xf && xf.length) {
      h += '<h3>현물 이관 (이수 / 이체)</h3>' + table([THL('구분'), THL('펀드'), '금액(억)', '건수', THL('일자')], xf.map((x) => `<tr>${L(x.s === '이수' ? '이수(유입)' : '이체(유출)')}${L(esc(x.f))}${N(x.amt, 0)}${N(x.n, 0)}${L(x.d)}</tr>`));
    }
    return h + '<p class="note">※ 순유출입 = Σ(좌수 변동 × 기준가/1000), 신규 설정액·해지 시 잔액 포함. 운용손익 추정 = 기말 − 기초 − 순유출입.</p>';
  }

  function tradeRows(list) {
    return list.map((x) => `<tr>${L(x.d)}${L(esc(x.f))}${L(esc(x.i))}${L(esc(x.a))}${L(x.mat)}${N(x.my, 1)}${N(x.amt, 1)}${S(x.pnl, 2)}${S(x.pr, 2)}</tr>`);
  }
  function sTrade(p) {
    const T = p.tr;
    if (!T || T.empty) return empty('기간 중 채권 매매 내역이 없습니다.');
    const F = p.funds.filter((f) => f.tr && (f.tr.buy || f.tr.sell));
    let h = `<p>기간 중 매매 <b>${nf(T.n, 0)}건</b>, 매입 <b>${nf(T.buy, 0)}억</b> / 매도 <b>${nf(T.sell, 0)}억</b>, 실현손익 <b class="${cl(T.pnl)}">${sg(T.pnl, 1)}억</b>` + (isNum(T.pr) ? ` (매도금액 대비 ${sg(T.pr, 2)}%)` : '') + '.</p>';
    h += '<h3>펀드별 매매 현황</h3>' + table([THL('펀드'), '매입(억)', '매도(억)', '순매수(억)', '건수', '회전율(%)', '매입 가중만기(년)', '매도 가중만기(년)', '실현손익(억)', '손익률(%)'],
      F.map((f) => { const t = f.tr; return `<tr>${L(fname(f))}${N(t.buy, 1)}${N(t.sell, 1)}${S(t.net, 1)}${N(t.n, 0)}${N(t.to, 1)}${N(t.mb, 2)}${N(t.ms, 2)}${S(t.pnl, 2)}${S(t.pr, 2)}</tr>`; }));
    h += '<div class="grid2"><div><h3>잔존만기 구간별 매매</h3>' + table([THL('잔존만기'), '매입(억)', '매도(억)', '순매수(억)'], T.bk.map((b) => `<tr>${L(b.k)}${N(b.buy, 1)}${N(b.sell, 1)}${S(b.net, 1)}</tr>`))
      + '</div><div class="chart"><canvas id="cBk"></canvas></div></div>';
    h += '<h3>자산구분별 매매</h3>' + table([THL('자산구분'), '매입(억)', '매도(억)', '순매수(억)', '실현손익(억)', '건수'], T.asset.slice(0, 10).map((a) => `<tr>${L(esc(a.a))}${N(a.buy, 1)}${N(a.sell, 1)}${S(a.net, 1)}${S(a.pnl, 2)}${N(a.n, 0)}</tr>`));
    const head = [THL('일자'), THL('펀드'), THL('종목'), THL('자산'), THL('만기'), '잔존(년)', '결제액(억)', '손익(억)', '손익률(%)'];
    if (T.loss.length) h += '<h3>실현손실 상위 매도</h3>' + table(head, tradeRows(T.loss));
    if (T.gain.length) h += '<h3>실현이익 상위 매도</h3>' + table(head, tradeRows(T.gain));
    if (T.bigbuy.length) h += '<h3>대규모 매입</h3>' + table(head, tradeRows(T.bigbuy));
    return h + '<p class="note">※ 이수·이체(현물 이관)는 매매 규모·회전율에서 제외. 가중만기는 결제액 가중 잔존만기. 손익률 = 매매손익 ÷ 결제액.</p>';
  }

  function sDisc(p) {
    const F = p.funds.filter((f) => f.g === 'D');
    const rows = F.map((f) => `<tr>${L(fname(f))}${L(f.st === '해지' ? `해지 (${f.last})` : '운용 중')}${N(f.r, 3)}${N(f.rb, 3)}${S(f.ex, 1)}${N(f.ytd, 3)}${N(f.aumL, 0)}${S(f.flow, 0)}${N(f.d, 2)}${N(f.y, 2)}</tr>`);
    return table([THL('펀드'), THL('상태'), '기간 수익률(%)', 'BM(%)', '초과(bp)', '연초이후(%)', '최종 순자산(억)', '순유출입(억)', '듀레이션', 'YTM(%)'], rows)
      + '<p class="note">※ 일부 일임 펀드는 BM지수가 없어 초과수익을 산출하지 않습니다. 해지 펀드의 순자산은 최종 기준일 값.</p>';
  }

  function sOverseas(p) {
    const F = p.funds.filter((f) => f.g === 'O');
    const rows = F.map((f) => {
      const h = f.hg;
      const hr = h ? `${nf(h.start, 1)} → ${nf(h.end, 1)}` : '-';
      return `<tr>${L(fname(f))}${L(esc(f.m || '-'))}${N(f.aumL, 0)}${N(f.r, 3)}${N(f.rb, 3)}${S(f.ex, 1)}${S(f.ytdx, 1)}<td>${nf(f.d, 2)} / ${nf(f.db, 2)}</td><td>${hr}</td>${N(h ? h.med : null, 1)}${S(h ? h.fxeff : null, 1)}</tr>`;
    });
    const fx = p.mkt.vals.usdkrw;
    return (fx ? `<p>원/달러 ${nf(fx[0], 1)}원 → ${nf(fx[1], 1)}원 (<span class="${cl(fx[1] - fx[0])}">${sg((fx[1] / fx[0] - 1) * 100, 2)}%</span>).</p>` : '')
      + table([THL('펀드'), THL('운용사'), '순자산(억)', '수익률(%)', 'BM(%)', '초과(bp)', '연초 초과(bp)', '듀레이션 펀드/BM', '헤지 기초→기말(%)', '헤지 중앙값(%)', '환노출 효과(bp)'], rows)
      + '<div class="chart"><canvas id="cHg"></canvas></div>'
      + '<p class="note">※ 운용사명은 헤지비율 자료 파일명 기준(해외 3호는 헤지비율 자료 없음). 헤지비율이 며칠간 급등했다 되돌아오는 구간은 선물환 롤오버 시 신·구 계약이 함께 잡힌 것으로 보여(추정) 기간 대표값은 중앙값을 사용. 환노출 효과 추정 = (1 − 중앙값 헤지비율) × 원/달러 변화율 (BM의 헤지 구조는 미반영, 참고용).</p>';
  }

  function sYtd(p) {
    const U = uFunds(p).filter((f) => isNum(f.ytdx)).sort((a, b) => b.ytdx - a.ytdx);
    const rows = U.map((f, i) => `<tr><td>${i + 1}</td>${L(esc(f.m))}${L(fname(f))}${L(f.first > META.dmin ? `${md(f.first)} 설정` : '연초')}${N(f.ytd, 3)}${N(f.ytdb, 3)}${S(f.ytdx, 1)}</tr>`);
    return '<div class="grid2"><div class="chart tall"><canvas id="cCumB"></canvas></div><div class="chart tall"><canvas id="cCumL"></canvas></div></div>'
      + table(['순위', THL('운용사'), THL('펀드'), THL('기산'), '누적 수익률(%)', 'BM(%)', '누적 초과(bp)'], rows)
      + `<p class="note">※ ${META.dmin} 기준가(또는 설정일) 대비 ${p.e}까지 누적.</p>`;
  }

  function sOpinion(p) {
    const chk = p.chk.length ? p.chk.map((c) => `<li>${c}</li>`).join('') : '<li>특이 점검사항 없음</li>';
    return `<h3>종합 의견</h3><ul class="pts">${p.cm.map((c) => `<li>${c}</li>`).join('')}</ul>`
      + `<h3>점검 필요사항</h3><ul class="pts">${chk}</ul>`
      + '<p class="note">※ 코멘트와 점검사항은 수치 기준으로 자동 생성된 참고용 문구입니다. 점검 기준: 듀레이션 갭 ±0.3년, 기간 초과수익 ' + (state.kind === 'W' ? '−10bp' : '−20bp') + ' 이하, 연초 이후 초과 −30bp 이하, 실현손실 10억 이상, 회전율 ' + (state.kind === 'W' ? '15%' : '40%') + ' 이상, 단기자산 5% 이상, 헤지비율 ±10%p 변동.</p>';
  }

  function build(p) {
    const has = (g) => p.funds.some((f) => f.g === g);
    const S_ = [
      ['s-sum', '요약', sSummary(p), false],
      ['s-mkt', '시장 환경', sMarket(p), false],
      ['s-perf', '펀드별 성과 (국내채권형 유니버스)', sPerf(p), true],
      ['s-attr', '성과요인 분해 (추정)', sAttr(p), false],
      ['s-mgr', '운용사별 비교', sMgr(p), true],
      ['s-pos', '포지션: 듀레이션 · YTM · 자산구성', sPos(p), false],
      ['s-flow', '순자산 및 자금 유출입', sFlow(p), true],
      ['s-trade', '매매 동향 및 실현손익', sTrade(p), true]
    ];
    if (has('D')) S_.push(['s-disc', '일임 채권형', sDisc(p), true]);
    if (has('O')) S_.push(['s-os', '해외채권형 및 환헤지', sOverseas(p), true]);
    S_.push(['s-ytd', '연초 이후 누적 성과', sYtd(p), true]);
    S_.push(['s-op', '종합 의견 및 점검사항', sOpinion(p), true]);
    return S_.map((s, i) => ({ id: s[0], title: s[1], html: `<section id="${s[0]}" class="${s[3] ? 'pb' : ''}"><h2><span>${i + 1}.</span>${s[1]}</h2>${s[2]}</section>`, n: i + 1 }));
  }

  // ---------- 차트 ----------
  function draw(p) {
    const [s, e] = windowIdx(p);
    const labels = sliceLabels(s, e);
    const band = bandOpt(p, s);
    const mk = (k) => (DD.mkt[k] || []).slice(s, e + 1);
    const pct = (v) => Number(v).toFixed(2) + '%';
    mkChart('cMkt1', lineCfg(labels, [{ label: '국고 3년', data: mk('ktb3') }, { label: '국고 10년', data: mk('ktb10') }, { label: '국고 30년', data: mk('ktb30') }], '국내 금리 추이 (음영: 보고 기간)', band, pct));
    mkChart('cMkt2', lineCfg(labels, [{ label: '美국채 10년(좌)', data: mk('ust10') }, { label: '원/달러(우)', data: mk('usdkrw'), yAxisID: 'y2', borderColor: COLORS[2], backgroundColor: COLORS[2] }], '美국채 10년 · 원/달러', band, pct, (v) => Number(v).toLocaleString('ko-KR')));

    const U = uFunds(p);
    const Ux = U.filter((f) => isNum(f.ex));
    if (Ux.length) {
      mkChart('cEx', { type: 'bar', data: { labels: Ux.map((f) => f.n), datasets: [{ label: '기간 초과수익(bp)', data: Ux.map((f) => f.ex), backgroundColor: Ux.map((f) => f.ex >= 0 ? 'rgba(220,38,38,.7)' : 'rgba(37,99,235,.7)'), borderRadius: 4 }] },
        options: { plugins: { title: { display: true, text: '펀드별 BM 대비 초과수익 (bp)' }, legend: { display: false } } } });
    }
    const Ua = U.filter((f) => f.at);
    if (Ua.length) {
      mkChart('cAtt', { type: 'bar', data: { labels: Ua.map((f) => f.n), datasets: [
        { label: '캐리', data: Ua.map((f) => f.at.carry), backgroundColor: '#10b981' },
        { label: '듀레이션', data: Ua.map((f) => f.at.dur), backgroundColor: '#4f46e5' },
        { label: '기타(커브·종목·매매)', data: Ua.map((f) => f.at.res), backgroundColor: '#f59e0b' },
        { label: '초과수익', data: Ua.map((f) => f.ex), type: 'line', borderColor: '#0f172a', backgroundColor: '#0f172a', showLine: false, pointRadius: 4, pointStyle: 'rectRot' }] },
        options: { scales: { x: { stacked: true }, y: { stacked: true } }, plugins: { title: { display: true, text: '초과수익 요인분해 (bp, 추정)' } } } });
    }
    // 듀레이션 갭 추이 (은행형 / 생보형)
    ['은행', '생보'].forEach((t, j) => {
      const fs = U.filter((f) => f.t === t);
      const ds = fs.map((f) => ({ label: f.n, data: (DD.funds[f.c] || { dg: [] }).dg.slice(s, e + 1) }));
      mkChart(j ? 'cDgL' : 'cDgB', lineCfg(labels, ds, `듀레이션 갭 추이 (${t}형, 년)`, band, (v) => Number(v).toFixed(2)));
    });
    // 만기구간 매매
    if (p.tr && p.tr.bk) {
      mkChart('cBk', { type: 'bar', data: { labels: p.tr.bk.map((b) => b.k), datasets: [
        { label: '매입', data: p.tr.bk.map((b) => b.buy), backgroundColor: 'rgba(220,38,38,.65)' },
        { label: '매도', data: p.tr.bk.map((b) => -b.sell), backgroundColor: 'rgba(37,99,235,.65)' },
        { label: '순매수', data: p.tr.bk.map((b) => b.net), type: 'line', borderColor: '#0f172a', backgroundColor: '#0f172a', showLine: false, pointRadius: 4 }] },
        options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: (v) => Number(v).toLocaleString('ko-KR') } } }, plugins: { title: { display: true, text: '잔존만기 구간별 매입(+)/매도(−) (억원)' } } } });
    }
    // 환헤지
    const O = p.funds.filter((f) => f.g === 'O' && DD.hedge[f.c]);
    if (O.length) {
      const ds = O.map((f) => ({ label: `${f.n}${f.m ? ' (' + f.m + ')' : ''} 헤지비율(좌)`, data: DD.hedge[f.c].slice(s, e + 1) }));
      ds.push({ label: '원/달러(우)', data: mk('usdkrw'), yAxisID: 'y2', borderColor: '#94a3b8', backgroundColor: '#94a3b8', borderDash: [5, 4] });
      mkChart('cHg', lineCfg(labels, ds, '환헤지비율 · 원/달러', band, (v) => v + '%', (v) => Number(v).toLocaleString('ko-KR')));
    }
    // 누적 초과수익 (연초 이후)
    ['은행', '생보'].forEach((t, j) => {
      const fs = U.filter((f) => f.t === t);
      const ds = fs.map((f) => {
        const d = DD.funds[f.c];
        let f0 = -1;
        const arr = [];
        for (let i = 0; i <= e; i++) {
          const a = d.tri[i], b = d.bm[i];
          if (f0 < 0 && a != null && b != null) f0 = i;
          arr.push(f0 >= 0 && a != null && b != null ? Math.round((a / d.tri[f0] - b / d.bm[f0]) * 1e5) / 10 : null);
        }
        return { label: f.n, data: arr };
      });
      mkChart(j ? 'cCumL' : 'cCumB', lineCfg(DD.dates.slice(0, e + 1).map(md), ds, `연초 이후 누적 초과수익 (${t}형, bp)`, {}, (v) => v));
    });
  }

  // ---------- 렌더 ----------
  function fillSelect() {
    const list = D.periods[state.kind];
    $('#sel').innerHTML = list.map((p, i) => `<option value="${i}">${esc(p.label)}</option>`).join('');
    $('#sel').value = String(state.idx);
    document.querySelectorAll('#seg button').forEach((b) => b.classList.toggle('on', b.dataset.k === state.kind));
    $('#prev').disabled = state.idx >= list.length - 1;
    $('#next').disabled = state.idx <= 0;
  }

  function render() {
    charts.forEach((c) => c.destroy());
    charts = [];
    const p = D.periods[state.kind][state.idx];
    const kn = state.kind === 'W' ? '주간' : '월간';
    fillSelect();
    $('#badge').textContent = `${kn} · ${p.label.replace(' · 진행중', ' (진행중)')} · 기준가 ${p.b} → ${p.e}`;
    $('#info').textContent = `데이터 ${META.dmin} ~ ${META.dmax} · 생성 ${META.gen}`;
    document.title = `${p.title} | 위탁운용 운용분석보고서`;
    window.REPORT_FNAME = `위탁운용_${kn}운용분석_${p.id.slice(1)}`;
    const secs = build(p);
    $('#toc').innerHTML = secs.map((s) => `<a href="#${s.id}">${s.n}. ${s.title.replace(/ \(.*\)$/, '')}</a>`).join('');
    $('#report').innerHTML = secs.map((s) => s.html).join('');
    $('#foot').innerHTML = `원자료: ${META.src.map(esc).join(' · ')}<br>시장: 한국은행 ECOS, FRED, 서울외국환중개 · 생성: ${META.gen}`
      + '<br><a href="report_holdings.html">📎 25년말 보유내역 기준 포트폴리오 분석(종목·만기구간·섹터) 보기</a>';
    draw(p);
    try { history.replaceState(null, '', '#' + p.id); } catch (e) { /* file:// 등 */ }
  }

  function selectById(id) {
    for (const k of ['W', 'M']) {
      const i = D.periods[k].findIndex((p) => p.id === id);
      if (i >= 0) { state.kind = k; state.idx = i; return true; }
    }
    return false;
  }

  document.querySelectorAll('#seg button').forEach((b) => b.addEventListener('click', () => {
    if (state.kind === b.dataset.k) return;
    state.kind = b.dataset.k;
    state.idx = firstComplete(state.kind);
    render();
  }));
  $('#sel').addEventListener('change', (ev) => { state.idx = +ev.target.value; render(); });
  $('#prev').addEventListener('click', () => { if (state.idx < D.periods[state.kind].length - 1) { state.idx++; render(); } });
  $('#next').addEventListener('click', () => { if (state.idx > 0) { state.idx--; render(); } });
  window.addEventListener('beforeprint', () => charts.forEach((c) => c.resize()));
  window.addEventListener('afterprint', () => charts.forEach((c) => c.resize()));

  if (!selectById((location.hash || '').slice(1))) { state.kind = 'W'; state.idx = firstComplete('W'); }
  render();
  window.__reportState = state;
  window.__reportRender = render;
})();
