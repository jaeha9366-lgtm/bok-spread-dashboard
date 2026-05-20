import pandas as pd
import json
from datetime import datetime, timedelta
import requests

def fetch_data_for_item(api_key, item_code, start_date, end_date):
    """
    ECOS API를 통해 특정 항목의 환율 데이터를 조회합니다.
    """
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

def process_exchange_rates(api_key):
    print("\n--- 원/달러 환율 데이터 수집 시작 ---")
    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=3 * 365) # 최근 3년
    
    start_date = start_dt.strftime("%Y%m%d")
    end_date = end_dt.strftime("%Y%m%d")
    
    print("Fetching 15:30 주간 종가...")
    rows_1530 = fetch_data_for_item(api_key, "0000003", start_date, end_date)
    
    print("Fetching 02:00 야간 종가...")
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
    
    # 웹 렌더링용 date 문자열(YYYY-MM-DD) 처리
    df_merged['date_str'] = df_merged['date'].dt.strftime('%Y-%m-%d')
    
    # 1. CSV 저장
    csv_filename = "usd_krw_3years.csv"
    # UI에서 쉽게 쓸 수 있도록 컬럼명 변경 후 저장
    df_export = df_merged.copy()
    df_export['날짜'] = df_export['date_str']
    df_export['15:30 종가'] = df_export['rate_1530']
    if 'rate_0200' in df_export:
        df_export['02:00 종가'] = df_export['rate_0200']
        export_cols = ['날짜', '15:30 종가', '02:00 종가']
    else:
        export_cols = ['날짜', '15:30 종가']
        
    df_export[export_cols].to_csv(csv_filename, index=False, encoding='utf-8-sig')
    print(f"Saved {csv_filename}")
    
    # 2. 엑셀 저장 (차트 포함)
    xlsx_filename = "usd_krw_3years.xlsx"
    try:
        with pd.ExcelWriter(xlsx_filename, engine='xlsxwriter') as writer:
            df_excel = df_export[export_cols]
            df_excel.to_excel(writer, sheet_name='USD_KRW_Data', index=False)
            
            workbook  = writer.book
            worksheet = writer.sheets['USD_KRW_Data']
            
            # 서식
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
            
            for col_num, value in enumerate(df_excel.columns.values):
                worksheet.write(0, col_num, value, header_format)
                
            worksheet.set_column('A:A', 15, date_format)
            worksheet.set_column('B:C', 18, num_format)
            worksheet.set_row(0, 24)
            worksheet.hide_gridlines(0)
            
            max_row = len(df_excel)
            min_val = float(df_merged['rate_1530'].min())
            max_val = float(df_merged['rate_1530'].max())
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
            chart_1530.set_x_axis({'name': '날짜', 'label_position': 'low', 'interval_unit': 60})
            chart_1530.set_y_axis({'name': '환율 (원)', 'min': y_min, 'max': y_max})
            chart_1530.set_legend({'position': 'none'})
            chart_1530.set_size({'width': 850, 'height': 400})
            worksheet.insert_chart('E2', chart_1530)
            
            # Chart 2: 02:00
            if 'rate_0200' in df_merged:
                chart_0200 = workbook.add_chart({'type': 'line'})
                chart_0200.add_series({
                    'name':       ['USD_KRW_Data', 0, 2],
                    'categories': ['USD_KRW_Data', 1, 0, max_row, 0],
                    'values':     ['USD_KRW_Data', 1, 2, max_row, 2],
                    'line':       {'color': '#ff7f0e', 'width': 2.0},
                })
                chart_0200.set_title({'name': '원/달러(USD/KRW) 야간 종가 추이 (02:00 KST)', 'name_font': {'name': '맑은 고딕', 'size': 14, 'bold': True}})
                chart_0200.set_x_axis({'name': '날짜', 'label_position': 'low', 'interval_unit': 60})
                chart_0200.set_y_axis({'name': '환율 (원)', 'min': y_min, 'max': y_max})
                chart_0200.set_legend({'position': 'none'})
                chart_0200.set_size({'width': 850, 'height': 400})
                worksheet.insert_chart('E23', chart_0200)
                
        print(f"Saved {xlsx_filename} with native charts.")
    except Exception as e:
        print(f"Error saving {xlsx_filename}: {e}")

    # 3. HTML 생성 (exchange.html)
    # df_merged의 데이터를 JSON으로 변환
    data_list = []
    for _, row in df_merged.iterrows():
        item = {'date': row['date_str'], 'rate_1530': row['rate_1530']}
        if 'rate_0200' in df_merged and pd.notna(row['rate_0200']):
            item['rate_0200'] = row['rate_0200']
        data_list.append(item)
        
    latest = df_merged.iloc[-1]
    stats = {
        'latest_date': latest['date_str'],
        'latest_1530': latest['rate_1530'],
        'latest_0200': latest['rate_0200'] if 'rate_0200' in latest and pd.notna(latest['rate_0200']) else None
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
    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
    
    <style>
        :root {{
            --bg-base: #080b11;
            --bg-surface: rgba(13, 18, 30, 0.75);
            --bg-card: rgba(22, 30, 49, 0.45);
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

        body {{
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-body);
            min-height: 100vh;
            padding: 2rem 1.5rem;
            margin: 0;
            overflow-y: auto; /* Allow scrolling inside iframe */
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-glow);
            padding-bottom: 1.5rem;
        }}

        .brand h1 {{
            font-family: var(--font-display);
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #3b82f6 0%, #f59e0b 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .brand p {{
            color: var(--text-secondary);
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }}

        .btn {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-glow);
            color: var(--text-primary);
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s;
            backdrop-filter: blur(10px);
        }}
        .btn:hover {{
            background: rgba(16, 185, 129, 0.1);
            border-color: rgba(16, 185, 129, 0.4);
            color: #34d399;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
        }}

        .metric-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border-glow);
            border-radius: 16px;
            padding: 1.5rem;
            position: relative;
        }}
        
        .metric-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0;
            width: 4px; height: 100%;
        }}
        .card-1530::before {{ background: var(--color-1530); }}
        .card-0200::before {{ background: var(--color-0200); }}

        .metric-label {{ font-size: 0.85rem; color: var(--text-secondary); font-weight: 600; }}
        .metric-value {{ font-family: var(--font-display); font-size: 2.1rem; font-weight: 700; margin-top: 0.5rem; }}
        
        .panel {{
            background: var(--bg-surface);
            border: 1px solid var(--border-glow);
            border-radius: 16px;
            padding: 1.75rem;
            margin-bottom: 2rem;
        }}
        .panel-title {{ font-family: var(--font-display); font-size: 1.25rem; font-weight: 600; margin-bottom: 1.5rem; }}
        
        .chart-container {{ position: relative; width: 100%; height: 400px; }}
        
        /* Table Design */
        .table-container {{
            overflow-x: auto;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.05);
            margin-top: 1rem;
            max-height: 400px;
            overflow-y: auto;
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th {{
            background: rgba(255, 255, 255, 0.03);
            color: var(--text-secondary);
            font-weight: 600;
            padding: 1rem;
            text-align: right;
            position: sticky;
            top: 0;
            z-index: 10;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        th:first-child {{ text-align: left; }}
        td {{ padding: 0.85rem 1rem; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.02); color: var(--text-primary); }}
        td:first-child {{ text-align: left; color: var(--text-secondary); font-weight: 500; }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.015); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>Exchange Rate Dashboard</h1>
                <p>최근 3개년 원/달러 (USD/KRW) 주·야간 종가 추이 (기준: <span id="latest-date"></span>)</p>
            </div>
            <button class="btn" onclick="window.open('usd_krw_3years.xlsx')">📥 엑셀(XLSX) 다운로드</button>
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
        const rawData = {data_json};
        const stats = {stats_json};
        
        document.getElementById('latest-date').textContent = stats.latest_date;
        document.getElementById('val-1530').textContent = stats.latest_1530 ? stats.latest_1530.toLocaleString(undefined, {{minimumFractionDigits: 2}}) + ' 원' : '-';
        document.getElementById('val-0200').textContent = stats.latest_0200 ? stats.latest_0200.toLocaleString(undefined, {{minimumFractionDigits: 2}}) + ' 원' : '미제공';

        // Render Table
        const tbody = document.querySelector('#dataTable tbody');
        // 역순으로 렌더링 (최신이 위로)
        const tableData = [...rawData].reverse();
        tableData.forEach(row => {{
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${{row.date}}</td>
                <td>${{row.rate_1530 ? row.rate_1530.toFixed(2) : '-'}}</td>
                <td>${{row.rate_0200 ? row.rate_0200.toFixed(2) : '-'}}</td>
            `;
            tbody.appendChild(tr);
        }});

        // Render Chart
        const ctx = document.getElementById('exchangeChart').getContext('2d');
        const labels = rawData.map(d => d.date);
        const data1530 = rawData.map(d => d.rate_1530);
        const data0200 = rawData.map(d => d.rate_0200 || null);

        new Chart(ctx, {{
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
                interaction: {{
                    mode: 'index',
                    intersect: false,
                }},
                plugins: {{
                    legend: {{
                        labels: {{ color: '#94a3b8', font: {{ family: 'Inter', size: 12 }} }}
                    }},
                    tooltip: {{
                        backgroundColor: 'rgba(13, 18, 30, 0.9)',
                        titleColor: '#f8fafc',
                        bodyColor: '#e2e8f0',
                        borderColor: 'rgba(99, 102, 241, 0.3)',
                        borderWidth: 1,
                        padding: 10
                    }}
                }},
                scales: {{
                    x: {{
                        grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                        ticks: {{ color: '#64748b', maxTicksLimit: 12 }}
                    }},
                    y: {{
                        grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
                        ticks: {{ color: '#64748b' }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>'''
