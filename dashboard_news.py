import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re

def process_news():
    print("\n--- 채권/외환 뉴스 RSS 피드 수집 시작 ---")
    url = "https://news.einfomax.co.kr/rss/S1N16.xml"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        xml_content = response.content
    except Exception as e:
        print(f"Error fetching RSS feed: {e}")
        return

    try:
        root = ET.fromstring(xml_content)
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return

    # 현재 시간을 기준으로 오늘과 어제 날짜 계산
    now = datetime.now()
    
    # 만약 오후 6시 이전(00:00~18:00)에 실행된다면, '오늘'의 주간은 아직 진행중이다.
    # 스케줄러가 매일 18:00에 돈다고 가정하면, 
    # - 주간(Daytime): 오늘 08:00:00 ~ 18:00:00
    # - 야간(Nighttime): 어제 18:00:00 ~ 오늘 08:00:00
    # 이렇게 나누는 것이 가장 직관적.
    
    today_0800 = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today_1800 = now.replace(hour=18, minute=0, second=0, microsecond=0)
    yesterday_1800 = today_1800 - timedelta(days=1)
    
    daytime_news = []
    nighttime_news = []
    other_news = [] # 기준 밖의 과거 뉴스
    
    items = root.findall('.//item')
    print(f"Found {len(items)} news articles in RSS feed.")
    
    for item in items:
        title = item.find('title').text if item.find('title') is not None else "No Title"
        link = item.find('link').text if item.find('link') is not None else "#"
        description = item.find('description').text if item.find('description') is not None else ""
        author = item.find('author').text if item.find('author') is not None else "Unknown"
        pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ""
        
        # pub_date_str 형식: "2026-05-20 23:28:46"
        try:
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pub_date = now # 파싱 실패 시 예외처리
            
        # HTML 렌더링용 날짜 포맷
        display_date = pub_date.strftime("%m/%d %H:%M")
        
        # 깔끔한 텍스트를 위해 CDATA, 불필요한 태그 등 제거
        # Description이 너무 길 경우 150자로 자르기
        clean_desc = re.sub(r'<[^>]+>', '', description).strip()
        if len(clean_desc) > 150:
            clean_desc = clean_desc[:147] + "..."
            
        news_obj = {
            "title": title.strip(),
            "link": link.strip(),
            "description": clean_desc,
            "author": author.strip(),
            "date": display_date,
            "raw_date": pub_date
        }
        
        # 카테고리 분류
        if today_0800 <= pub_date <= today_1800:
            daytime_news.append(news_obj)
        elif yesterday_1800 <= pub_date < today_0800:
            nighttime_news.append(news_obj)
        else:
            # 최근 24시간 외의 뉴스도 너무 적을 경우를 대비해 최신순으로 기타 배열
            other_news.append(news_obj)
            
    # RSS 자체적으로 최신순 정렬되어 있지만, 한번 더 정렬
    daytime_news.sort(key=lambda x: x['raw_date'], reverse=True)
    nighttime_news.sort(key=lambda x: x['raw_date'], reverse=True)
    other_news.sort(key=lambda x: x['raw_date'], reverse=True)
    
    # 만약 주야간 뉴스가 없다면, other_news로 대체
    if len(daytime_news) == 0 and len(nighttime_news) == 0:
        print("최근 24시간 내 뉴스가 없어 전체 최신 뉴스를 사용합니다.")
        half = len(other_news) // 2
        daytime_news = other_news[:half]
        nighttime_news = other_news[half:]
        
    print(f"분류 완료 - 주간: {len(daytime_news)}건, 야간: {len(nighttime_news)}건")
    
    # HTML 생성
    html_content = generate_news_html(daytime_news, nighttime_news, now.strftime("%Y-%m-%d %H:%M KST"))
    
    with open("news.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Saved news.html successfully.")

def generate_news_html(daytime_news, nighttime_news, update_time):
    # 카드 생성 헬퍼 함수
    def build_cards(news_list, empty_msg="해당 시간대에 기사가 없습니다."):
        if not news_list:
            return f"<div class='empty-state'>{empty_msg}</div>"
        
        cards = ""
        for news in news_list:
            cards += f"""
            <a href="{news['link']}" target="_blank" class="news-card">
                <div class="news-meta">
                    <span class="news-date">🕒 {news['date']}</span>
                    <span class="news-author">✍️ {news['author']}</span>
                </div>
                <h3 class="news-title">{news['title']}</h3>
                <p class="news-desc">{news['description']}</p>
                <div class="news-action">기사 원문 보기 ➔</div>
            </a>
            """
        return cards

    daytime_html = build_cards(daytime_news)
    nighttime_html = build_cards(nighttime_news)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>채권/외환 주요 기사 요약</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-base: #080b11;
            --bg-surface: rgba(13, 18, 30, 0.75);
            --bg-card: rgba(22, 30, 49, 0.45);
            --border-glow: rgba(99, 102, 241, 0.15);
            --border-hover: rgba(99, 102, 241, 0.4);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --color-day: #3b82f6;
            --color-night: #a855f7;
            --font-display: 'Outfit', sans-serif;
            --font-body: 'Inter', sans-serif;
        }}

        body {{ background-color: var(--bg-base); color: var(--text-primary); font-family: var(--font-body); min-height: 100vh; padding: 2rem 1.5rem; margin: 0; overflow-y: auto; }}
        .container {{ max-width: 1400px; margin: 0 auto; display: flex; flex-direction: column; gap: 2rem; }}
        
        header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-glow); padding-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem; }}
        .brand h1 {{ font-family: var(--font-display); font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 0; }}
        .brand p {{ color: var(--text-secondary); font-size: 0.95rem; margin-top: 0.25rem; }}
        
        .update-badge {{ background: rgba(255,255,255,0.05); border: 1px solid var(--border-glow); padding: 0.5rem 1rem; border-radius: 20px; font-size: 0.85rem; color: var(--text-secondary); }}

        .news-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
        @media (max-width: 1024px) {{ .news-grid {{ grid-template-columns: 1fr; }} }}

        .news-column {{ display: flex; flex-direction: column; gap: 1.25rem; }}
        .column-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; padding-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        
        .icon-day {{ color: var(--color-day); font-size: 1.5rem; }}
        .icon-night {{ color: var(--color-night); font-size: 1.5rem; }}
        
        .column-title {{ font-family: var(--font-display); font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }}

        /* Card Styles */
        .news-card {{
            display: flex; flex-direction: column; gap: 0.75rem;
            background: var(--bg-surface);
            border: 1px solid var(--border-glow);
            border-radius: 12px;
            padding: 1.5rem;
            text-decoration: none;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }}
        
        .news-card::before {{
            content: ''; position: absolute; left: 0; top: 0; height: 100%; width: 4px;
            background: rgba(255,255,255,0.1); transition: all 0.3s;
        }}
        
        .col-day .news-card:hover::before {{ background: var(--color-day); }}
        .col-night .news-card:hover::before {{ background: var(--color-night); }}

        .news-card:hover {{
            transform: translateY(-4px);
            border-color: var(--border-hover);
            box-shadow: 0 10px 25px rgba(0,0,0,0.4);
            background: var(--bg-card);
        }}

        .news-meta {{ display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-muted); font-weight: 500; }}
        .news-title {{ font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin: 0; line-height: 1.4; transition: color 0.2s; }}
        .news-card:hover .news-title {{ color: #e2e8f0; }}
        
        .news-desc {{ font-size: 0.9rem; color: var(--text-secondary); margin: 0; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
        
        .news-action {{ font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-top: 0.5rem; transition: color 0.2s; text-align: right; }}
        .col-day .news-card:hover .news-action {{ color: var(--color-day); }}
        .col-night .news-card:hover .news-action {{ color: var(--color-night); }}

        .empty-state {{ padding: 3rem; text-align: center; color: var(--text-muted); background: rgba(255,255,255,0.02); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1); }}

    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>Bond & FX News Briefing</h1>
                <p>연합인포맥스 주요 기사 요약</p>
            </div>
            <div class="update-badge">
                🔄 최종 업데이트: {update_time}
            </div>
        </header>

        <div class="news-grid">
            <div class="news-column col-day">
                <div class="column-header">
                    <span class="icon-day">☀️</span>
                    <span class="column-title">주간 주요 기사 (08:00 ~ 18:00)</span>
                </div>
                {daytime_html}
            </div>
            
            <div class="news-column col-night">
                <div class="column-header">
                    <span class="icon-night">🌙</span>
                    <span class="column-title">야간 주요 기사 (전일 18:00 ~ 08:00)</span>
                </div>
                {nighttime_html}
            </div>
        </div>
    </div>
</body>
</html>"""

if __name__ == "__main__":
    process_news()
