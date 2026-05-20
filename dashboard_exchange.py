import pandas as pd
import json
from datetime import datetime, timedelta
import requests

def fetch_data_for_item(api_key, item_code, start_date, end_date):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/2000/731Y003/D/{start_date}/{end_date}/{item_code}"
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if "StatisticSearch" in data and "row" in data["StatisticSearch"]:
                return data["StatisticSearch"]["row"]
    except Exception as e:
        print(f"Error fetching exchange rate data ({item_code}): {e}")
    return []

def generate_excel(df, xlsx_filename):
    try:
        with pd.ExcelWriter(xlsx_filename, engine='xlsxwriter') as writer:
            export_cols = ['날짜', '15:30 종가']
            has_0200 = '02:00 종가' in df.columns
            if has_0200:
                export_cols.append('02:00 종가')
                
            df_excel = df[export_cols]
            df_excel.to_excel(writer, sheet_name='USD_KRW_Data', index=False)
            
            workbook  = writer.book
            worksheet = writer.sheets['USD_KRW_Data']
            
            header_format = workbook.add_format({
                'bold': True, 'align': 'center', 'valign': 'vcenter',
                'fg_color': '#f2f4f7', 'border': 1, 'border_color': '#d1d5db',
                'font_name': '맑은 고딕', 'font_size': 11
            })
            date_format = workbook.add_format({
                'align': 'center', 'border': 1, 'border_color': '#e5e7eb',
                'font_name': 'Segoe UI', 'font_size': 10
            })
            num_format = workbook.add_format({
                'num_format': '#,##0.00', 'align': 'right', 'border': 1, 
                'border_color': '#e5e7eb', 'font_name': 'Segoe UI', 'font_size': 10
            })
            # (전일 야간) 꼬리표를 숫자에 달아주는 마법의 서식
            prev_num_format = workbook.add_format({
                'num_format': '#,##0.00 " (전일 야간)"', 'align': 'right', 'border': 1, 
                'border_color': '#e5e7eb', 'font_name': 'Segoe UI', 'font_size': 10, 'font_color': '#6b7280'
            })
            
            for col_num, value in enumerate(df_excel.columns.values):
                worksheet.write(0, col_num, value, header_format)
                
            # 날짜 열과 데이터 열 기본 서식 적용
            for row_num in range(len(df_excel)):
                worksheet.write(row_num + 1, 0, df_excel.iloc[row_num, 0], date_format)
                worksheet.write(row_num + 1, 1, df_excel.iloc[row_num, 1], num_format)
                if has_0200:
                    val = df_excel.iloc[row_num, 2]
                    if pd.notna(val):
                        # is_0200_prev 체크
                        is_prev = df['is_0200_prev'].iloc[row_num]
                        fmt = prev_num_format if is_prev else num_format
                        worksheet.write(row_num + 1, 2, val, fmt)
                    else:
                        worksheet.write_blank(row_num + 1, 2, None, num_format)
                
            worksheet.set_column('A:A', 15)
            worksheet.set_column('B:B', 18)
            if has_0200:
                worksheet.set_column('C:C', 26) # 꼬리표를 위해 폭 확대
                
            worksheet.set_row(0, 24)
            worksheet.hide_gridlines(0)
            
            max_row = len(df_excel)
            min_val = float(df['15:30 종가'].min())
            max_val = float(df['15:30 종가'].max())
            y_min = int(min_val - 20)
            y_max = int(max_val + 20)
            
            # Chart 1: 15:30
            chart_1530 = workbook.add_chart({'type': 'line'})
            chart_1530.add_series({
                'name':       ['USD_KRW_Data', 0, 1],
                'categories': ['USD_KRW_Data', 1, 0, max_row, 0],
                'values':     ['USD_KRW_Data', 1, 1, max_row, 1],
                'line':       {'color': '#1f77b4', 'width': 2.0},
            })
            chart_1530.set_title({'name': '원/달러(USD/KRW) 주간 종가 추이 (15:30 KST)', 'name_font': {'name': '맑은 고딕', 'size': 14, 'bold': True}})
            chart_1530.set_x_axis({'name': '날짜', 'label_position': 'low'})
            chart_1530.set_y_axis({'name': '환율 (원)', 'min': y_min, 'max': y_max})
            chart_1530.set_legend({'position': 'none'})
            chart_1530.set_size({'width': 850, 'height': 400})
            worksheet.insert_chart('E2', chart_1530)
            
            # Chart 2: 02:00
            if has_0200:
                chart_0200 = workbook.add_chart({'type': 'line'})
                chart_0200.add_series({
                    'name':       ['USD_KRW_Data', 0, 2],
                    'categories': ['USD_KRW_Data', 1, 0, max_row, 0],
                    'values':     ['USD_KRW_Data', 1, 2, max_row, 2],
                    'line':       {'color': '#ff7f0e', 'width': 2.0},
                })
                chart_0200.set_title({'name': '원/달러(USD/KRW) 야간 종가 추이 (02:00 KST)', 'name_font': {'name': '맑은 고딕', 'size': 14, 'bold': True}})
                chart_0200.set_x_axis({'name': '날짜', 'label_position': 'low'})
                chart_0200.set_y_axis({'name': '환율 (원)', 'min': y_min, 'max': y_max})
                chart_0200.set_legend({'position': 'none'})
                chart_0200.set_size({'width': 850, 'height': 400})
                worksheet.insert_chart('E23', chart_0200)
                
        print(f"Saved {xlsx_filename} with native charts.")
    except Exception as e:
        print(f"Error saving {xlsx_filename}: {e}")


def process_exchange_rates(api_key):
    print("\n--- 원/달러 환율 데이터 수집 시작 ---")
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365)
    
    start_date = start_dt.strftime("%Y%m%d")
    end_date = end_dt.strftime("%Y%m%d")
    
    rows_1530 = fetch_data_for_item(api_key, "0000003", start_date, end_date)
    rows_0200 = fetch_data_for_item(api_key, "0000013", start_date, end_date)
    
    if not rows_1530:
        print("Warning: Failed to fetch 15:30 exchange rate data.")
        return
        
    df_1530 = pd.DataFrame(rows_1530)
    df_1530['date'] = pd.to_datetime(df_1530['TIME'], format='%Y%m%d')
    df_1530['rate_1530'] = pd.to_numeric(df_1530['DATA_VALUE'])
    df_1530 = df_1530[['date', 'rate_1530']]
    
    df_merged = df_1530
    
    if rows_0200:
        df_0200 = pd.DataFrame(rows_0200)
        df_0200['date'] = pd.to_datetime(df_0200['TIME'], format='%Y%m%d')
        df_0200['rate_0200'] = pd.to_numeric(df_0200['DATA_VALUE'])
        df_0200 = df_0200[['date', 'rate_0200']]
        
        df_merged = pd.merge(df_1530, df_0200, on='date', how='outer')
        
    df_merged = df_merged.sort_values(by='date').reset_index(drop=True)
    
    # 24년 7월 이전 데이터는 결측치로 유지하되 그 이후의 결측치는 ffill(옵션 B)
    if 'rate_0200' in df_merged.columns:
        first_valid = df_merged['rate_0200'].first_valid_index()
        df_merged['is_0200_prev'] = False
        if first_valid is not None:
            # 첫 유효값 발생 이후의 결측치 마스킹
            mask_missing = (df_merged.index > first_valid) & (df_merged['rate_0200'].isna())
            df_merged.loc[mask_missing, 'is_0200_prev'] = True
            df_merged['rate_0200'] = df_merged['rate_0200'].ffill()
    else:
        df_merged['is_0200_prev'] = False
        
    df_merged['date_str'] = df_merged['date'].dt.strftime('%Y-%m-%d')
    
    df_export = df_merged.copy()
    df_export['날짜'] = df_export['date_str']
    df_export['15:30 종가'] = df_export['rate_1530']
    if 'rate_0200' in df_export:
        df_export['02:00 종가'] = df_export['rate_0200']
    
    # 생성할 기간 설정
    periods = {
        '1m': 30,
        '3m': 90,
        '6m': 180,
        '1y': 365,
        '3y': 9999 # all
    }
    
    for label, days in periods.items():
        if days == 9999:
            df_slice = df_export.copy()
        else:
            cutoff = pd.to_datetime(end_date) - timedelta(days=days)
            df_slice = df_export[df_export['date'] >= cutoff].copy()
            
        if len(df_slice) > 0:
            generate_excel(df_slice, f"usd_krw_{label}.xlsx")
            
    # 전체 CSV 덤프
    export_cols = ['날짜', '15:30 종가']
    if '02:00 종가' in df_export:
        export_cols.append('02:00 종가')
    df_export[export_cols].to_csv("usd_krw_3years.csv", index=False, encoding='utf-8-sig')

    # HTML 뷰어용 JSON 데이터 추출 (최대 3년치 전체)
    data_list = []
    for _, row in df_merged.iterrows():
        item = {'date': row['date_str'], 'rate_1530': row['rate_1530']}
        if 'rate_0200' in df_merged and pd.notna(row['rate_0200']):
            item['rate_0200'] = row['rate_0200']
            item['is_prev'] = row['is_0200_prev']
        else:
            item['is_prev'] = False
        data_list.append(item)
        
    latest = df_merged.iloc[-1]
    stats = {
        'latest_date': latest['date_str'],
        'latest_1530': latest['rate_1530'],
        'latest_0200': latest['rate_0200'] if 'rate_0200' in latest and pd.notna(latest['rate_0200']) else None,
        'is_prev_latest': bool(latest['is_0200_prev']) if 'is_0200_prev' in latest else False
    }
    
    html_content = get_exchange_html(data_list, stats)
    with open("exchange.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Saved exchange.html")

def get_exchange_html(data_list, stats):
    data_json = json.dumps(data_list)
    stats_json = json.dumps(stats)
    
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>원/달러 환율 추이 대시보드</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <style>
        :root {{
            --bg-base: #080b11;
            --bg-surface: rgba(13, 18, 30, 0.75);
            --border-glow: rgba(99, 102, 241, 0.15);
            --border-hover: rgba(99, 102, 241, 0.35);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --color-1530: #3b82f6;
            --color-0200: #f59e0b;
            --font-display: 'Outfit', sans-serif;
            --font-body: 'Inter', sans-serif;
        }}

        body {{ background-color: var(--bg-base); color: var(--text-primary); font-family: var(--font-body); min-height: 100vh; padding: 2rem 1.5rem; margin: 0; overflow-y: auto; }}
        .container {{ max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 2rem; }}
        header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-glow); padding-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }}
        .brand h1 {{ font-family: var(--font-display); font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #3b82f6 0%, #f59e0b 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0; }}
        .brand p {{ color: var(--text-secondary); font-size: 0.95rem; margin-top: 0.25rem; }}

        .btn {{ background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border-glow); color: var(--text-primary); padding: 0.6rem 1.2rem; border-radius: 8px; font-size: 0.85rem; font-weight: 500; cursor: pointer; transition: all 0.3s; }}
        .btn:hover {{ background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.4); color: #34d399; }}

        /* Filter Controls */
        .controls-wrapper {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; }}
        .filter-group {{ display: flex; background: rgba(255,255,255,0.03); padding: 0.25rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }}
        .filter-btn {{ background: transparent; border: none; color: var(--text-secondary); padding: 0.45rem 1.2rem; border-radius: 6px; font-family: var(--font-body); font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
        .filter-btn.active {{ background: rgba(99, 102, 241, 0.2); color: #818cf8; }}

        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }}
        .metric-card {{ background: var(--bg-surface); border: 1px solid var(--border-glow); border-radius: 16px; padding: 1.5rem; position: relative; }}
        .metric-card::before {{ content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; }}
        .card-1530::before {{ background: var(--color-1530); }}
        .card-0200::before {{ background: var(--color-0200); }}
        .metric-label {{ font-size: 0.85rem; color: var(--text-secondary); font-weight: 600; }}
        .metric-value {{ font-family: var(--font-display); font-size: 2.1rem; font-weight: 700; margin-top: 0.5rem; }}
        
        .prev-tag {{ font-size: 0.9rem; color: var(--text-muted); font-weight: 500; font-family: var(--font-body); }}

        .panel {{ background: var(--bg-surface); border: 1px solid var(--border-glow); border-radius: 16px; padding: 1.75rem; margin-bottom: 2rem; }}
        .panel-title {{ font-family: var(--font-display); font-size: 1.25rem; font-weight: 600; margin-bottom: 1.5rem; }}
        .chart-container {{ position: relative; width: 100%; height: 400px; }}
        
        /* Table Design */
        .table-container {{ overflow-x: auto; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); margin-top: 1rem; max-height: 400px; overflow-y: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th {{ background: rgba(255,255,255,0.03); color: var(--text-secondary); font-weight: 600; padding: 1rem; text-align: right; position: sticky; top: 0; z-index: 10; backdrop-filter: blur(10px); border-bottom: 1px solid rgba(255,255,255,0.05); }}
        th:first-child {{ text-align: left; }}
        td {{ padding: 0.85rem 1rem; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.02); color: var(--text-primary); }}
        td:first-child {{ text-align: left; color: var(--text-secondary); font-weight: 500; }}
        tr:hover td {{ background: rgba(255,255,255,0.015); }}
        .cell-tag {{ color: #94a3b8; font-size: 0.8rem; margin-left: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>Exchange Rate Dashboard</h1>
                <p>원/달러 (USD/KRW) 주·야간 종가 추이 (기준: <span id="latest-date"></span>)</p>
            </div>
            
            <div class="controls-wrapper">
                <div class="filter-group" id="timeFilters">
                    <button class="filter-btn" data-days="30">1개월</button>
                    <button class="filter-btn" data-days="90">3개월</button>
                    <button class="filter-btn" data-days="180">6개월</button>
                    <button class="filter-btn active" data-days="365">1년</button>
                    <button class="filter-btn" data-days="1095">3년(전체)</button>
                </div>
                <button class="btn" id="downloadBtn" onclick="downloadExcel()">📥 엑셀(XLSX) 다운로드</button>
            </div>
        </header>

        <div class="metrics-grid">
            <div class="metric-card card-1530">
                <div class="metric-label">15:30 KST (주간 종가)</div>
                <div class="metric-value" id="val-1530">-</div>
            </div>
            <div class="metric-card card-0200">
                <div class="metric-label">02:00 KST (야간 종가, '24.07~)</div>
                <div class="metric-value" id="val-0200">-</div>
            </div>
        </div>

        <div class="panel">
            <div class="panel-title">📈 원/달러 시계열 추이 그래프</div>
            <div class="chart-container">
                <canvas id="exchangeChart"></canvas>
            </div>
        </div>
        
        <div class="panel">
            <div class="panel-title">📋 Raw Data Grid</div>
            <div class="table-container">
                <table id="dataTable">
                    <thead>
                        <tr>
                            <th>날짜 (Date)</th>
                            <th>15:30 주간 종가 (원)</th>
                            <th>02:00 야간 종가 (원)</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const fullData = {data_json};
        const stats = {stats_json};
        let chartInstance = null;
        let currentDays = 365; // default 1 year
        let currentFileLabel = '1y';
        
        document.getElementById('latest-date').textContent = stats.latest_date;
        document.getElementById('val-1530').textContent = stats.latest_1530 ? stats.latest_1530.toLocaleString(undefined, {{minimumFractionDigits: 2}}) + ' 원' : '-';
        
        const tagHtml = stats.is_prev_latest ? '<span class="prev-tag">(전일 야간)</span>' : '';
        document.getElementById('val-0200').innerHTML = stats.latest_0200 ? stats.latest_0200.toLocaleString(undefined, {{minimumFractionDigits: 2}}) + ' 원 ' + tagHtml : '미제공';

        // Filter Logic
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', (e) => {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                
                currentDays = parseInt(e.target.dataset.days);
                updateView();
            }});
        }});
        
        function downloadExcel() {{
            window.open(`usd_krw_${{currentFileLabel}}.xlsx`);
        }}

        function updateView() {{
            // 맵핑
            const mapping = {{30: '1m', 90: '3m', 180: '6m', 365: '1y', 1095: '3y'}};
            currentFileLabel = mapping[currentDays] || '1y';
            
            // 데이터 슬라이싱
            let filteredData = fullData;
            if(currentDays !== 1095) {{
                // 대략적인 일자 슬라이싱 (실제 영업일 기준이 아니므로 끝에서 자름)
                filteredData = fullData.slice(-currentDays);
            }}

            renderTable(filteredData);
            renderChart(filteredData);
        }}

        function renderTable(data) {{
            const tbody = document.querySelector('#dataTable tbody');
            tbody.innerHTML = '';
            
            // 표는 역순(최신이 위)
            const revData = [...data].reverse();
            
            revData.forEach(row => {{
                const tr = document.createElement('tr');
                const val1530 = row.rate_1530 ? row.rate_1530.toFixed(2) : '-';
                
                let val0200 = '-';
                if(row.rate_0200) {{
                    val0200 = row.rate_0200.toFixed(2);
                    if(row.is_prev) {{
                        val0200 += ' <span class="cell-tag">(전일 야간)</span>';
                    }}
                }}
                
                tr.innerHTML = `
                    <td>${{row.date}}</td>
                    <td>${{val1530}}</td>
                    <td>${{val0200}}</td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function renderChart(data) {{
            const labels = data.map(d => d.date);
            // 차트에는 숫자만 들어감
            const data1530 = data.map(d => d.rate_1530);
            const data0200 = data.map(d => d.rate_0200 || null);

            if(chartInstance) {{
                chartInstance.destroy();
            }}

            const ctx = document.getElementById('exchangeChart').getContext('2d');
            chartInstance = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [
                        {{
                            label: '15:30 주간 종가',
                            data: data1530,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            fill: true,
                            tension: 0.1
                        }},
                        {{
                            label: '02:00 야간 종가',
                            data: data0200,
                            borderColor: '#f59e0b',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            spanGaps: true,
                            tension: 0.1
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{ mode: 'index', intersect: false }},
                    plugins: {{
                        legend: {{ labels: {{ color: '#94a3b8', font: {{ family: 'Inter', size: 12 }} }} }},
                        tooltip: {{
                            backgroundColor: 'rgba(13, 18, 30, 0.9)',
                            titleColor: '#f8fafc',
                            bodyColor: '#e2e8f0',
                            borderColor: 'rgba(99, 102, 241, 0.3)',
                            borderWidth: 1,
                            padding: 10,
                            callbacks: {{
                                label: function(context) {{
                                    let label = context.dataset.label || '';
                                    if (label) {{ label += ': '; }}
                                    if (context.parsed.y !== null) {{
                                        label += context.parsed.y.toFixed(2);
                                        // 툴팁에서 (전일 야간) 표시
                                        if (context.datasetIndex === 1) {{
                                            const dataPoint = data[context.dataIndex];
                                            if (dataPoint && dataPoint.is_prev) {{
                                                label += ' (전일 야간)';
                                            }}
                                        }}
                                    }}
                                    return label;
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{ grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#64748b', maxTicksLimit: 12 }} }},
                        y: {{ grid: {{ color: 'rgba(255, 255, 255, 0.05)' }}, ticks: {{ color: '#64748b' }} }}
                    }}
                }}
            }});
        }}

        // 초기 로딩 시 1년치 실행
        updateView();
    </script>
</body>
</html>'''
