import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup

def summarize_article(url, fallback_text):
    """
    기사 원문 링크(url)에 접속하여 본문을 스크래핑한 뒤,
    첫 2~3개의 완전한 문장으로 요약하여 반환합니다.
    크롤링 실패 시 fallback_text(RSS description)를 반환합니다.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # 연합인포맥스 기사 본문 div 추출
            article_div = soup.find('div', id='article-view-content-div')
            if article_div:
                paragraphs = article_div.find_all('p')
                text = " ".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                if not text:
                    text = article_div.get_text(separator=" ", strip=True)
                
                # 기자 이메일, 불필요한 문구 등을 필터링하며 문장 쪼개기
                sentences = [s.strip() + "." for s in text.split(". ") if s.strip()]
                
                # 핵심 리드문(처음 2~3문장) 결합
                # 기사 첫 문단이 보통 가장 중요하므로 앞의 2문장을 취함. 
                # 합쳐서 너무 짧으면(100자 이하) 3문장까지 취함.
                if len(sentences) >= 1:
                    summary = sentences[0]
                    if len(sentences) > 1:
                        summary += " " + sentences[1]
                    if len(summary) < 100 and len(sentences) > 2:
                        summary += " " + sentences[2]
                        
                    # 괄호(기자 이름 등) 시작 부분 제거 등 추가 클리닝
                    summary = re.sub(r'^\([^\)]+\)\s*', '', summary)
                    return summary
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        
    # 스크래핑 실패 시 기존처럼 정제만 해서 리턴
    clean_fallback = re.sub(r'<[^>]+>', '', fallback_text).strip()
    return clean_fallback

def process_news():
    print("\n--- 채권/외환 뉴스 RSS 피드 수집 및 요약 시작 ---")
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

    now = datetime.now()
    today_0800 = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today_1800 = now.replace(hour=18, minute=0, second=0, microsecond=0)
    yesterday_1800 = today_1800 - timedelta(days=1)
    
    daytime_news = []
    nighttime_news = []
    other_news = []
    
    items = root.findall('.//item')
    print(f"Found {len(items)} news articles in RSS feed. Starting summarization...")
    
    for item in items:
        title = item.find('title').text if item.find('title') is not None else "No Title"
        link = item.find('link').text if item.find('link') is not None else "#"
        description = item.find('description').text if item.find('description') is not None else ""
        author = item.find('author').text if item.find('author') is not None else "Unknown"
        pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ""
        
        try:
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pub_date = now
            
        display_date = pub_date.strftime("%m/%d %H:%M")
        
        # 기사 본문을 스크래핑하여 완결된 문장으로 요약
        clean_desc = summarize_article(link, description)
            
        news_obj = {
            "title": title.strip(),
            "link": link.strip(),
            "description": clean_desc,
            "author": author.strip(),
            "date": display_date,
            "raw_date": pub_date
        }
        
        if today_0800 <= pub_date <= today_1800:
            daytime_news.append(news_obj)
        elif yesterday_1800 <= pub_date < today_0800:
            nighttime_news.append(news_obj)
        else:
            other_news.append(news_obj)
            
    daytime_news.sort(key=lambda x: x['raw_date'], reverse=True)
    nighttime_news.sort(key=lambda x: x['raw_date'], reverse=True)
    other_news.sort(key=lambda x: x['raw_date'], reverse=True)
    
    if len(daytime_news) == 0 and len(nighttime_news) == 0:
        print("최근 24시간 내 뉴스가 없어 전체 최신 뉴스를 사용합니다.")
        half = len(other_news) // 2
        daytime_news = other_news[:half]
        nighttime_news = other_news[half:]
        
    print(f"요약 완료 - 주간: {len(daytime_news)}건, 야간: {len(nighttime_news)}건")
    
    html_content = generate_news_html(daytime_news, nighttime_news, now.strftime("%Y-%m-%d %H:%M KST"))
    
    with open("news.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Saved news.html successfully.")

def generate_news_html(daytime_news, nighttime_news, update_time):
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
                <div class="news-desc-container">
                    <p class="news-desc">{news['description']}</p>
                </div>
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
        
        /* Removed line-clamp to show full summary sentences */
        .news-desc-container {{ background: rgba(0,0,0,0.15); padding: 1rem; border-radius: 8px; border-left: 2px solid rgba(255,255,255,0.05); }}
        .news-desc {{ font-size: 0.95rem; color: var(--text-secondary); margin: 0; line-height: 1.6; word-break: keep-all; }}
        
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
                <p>연합인포맥스 주요 기사 자동 요약 (완결문)</p>
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
