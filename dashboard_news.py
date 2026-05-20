import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re
import time
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from google import genai

# .env 파일 로드
load_dotenv()

# Gemini API 초기화
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print("Gemini API (google.genai) initialized successfully.")
else:
    print("Warning: GEMINI_API_KEY not found. Falling back to text extraction mode.")


def scrape_article_body(url):
    """기사 원문 링크를 방문하여 본문 텍스트를 추출합니다."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            article_div = soup.find('div', id='article-view-content-div')
            if article_div:
                text = article_div.get_text(separator=" ", strip=True)
                # 기자 연락처, 광고성 문구 등 후미 정제
                text = re.sub(r'\([\w@\. ]+\)\s*$', '', text).strip()
                return text[:2000]  # 토큰 절약을 위해 최대 2000자
    except Exception as e:
        print(f"  Scraping error for {url}: {e}")
    return ""


def ai_summarize(title, body, rss_desc=""):
    """Gemini API를 활용해 기사 핵심을 2~3문장으로 재구성합니다.
    body 스크래핑 실패 시 rss_desc(부분 본문)로 대체합니다."""
    if not gemini_client:
        return None

    # 사용 가능한 컨텍스트 준비 (스크래핑 본문 우선, 없으면 RSS 발췌)
    context = body if body else rss_desc
    if not context:
        return None

    prompt = f"""다음은 한국 채권/외환 금융 뉴스 기사의 제목과 본문 발췌입니다.
기사를 읽고 핵심 내용을 금융 전문가 시각에서 2~3문장으로 간결하게 재구성해 주세요.

규칙:
- 기사 문장을 그대로 복사하지 말고, 핵심 사실과 시장 영향을 자연스럽게 재구성하세요.
- 금리, 환율, bp 등 구체적인 수치가 있으면 반드시 포함하세요.
- 마크다운 기호(*,# 등) 없이 순수 텍스트로 작성하세요.
- 2~3문장으로 마무리하세요.

[제목] {title}

[본문/발췌]
{context[:1500]}

[요약]"""

    try:
        # 429 발생 시 최대 2회 재시도 (대기 후)
        for attempt in range(3):
            try:
                response = gemini_client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
                summary = response.text.strip()
                # 마크다운 기호 후처리 제거
                summary = summary.replace('**', '').replace('##', '').replace('*', '')
                return summary
            except Exception as inner_e:
                err_str = str(inner_e)
                if '429' in err_str and attempt < 2:
                    wait_sec = 60  # 1분 대기 후 재시도
                    print(f"  Rate limit hit. Waiting {wait_sec}s before retry ({attempt+1}/2)...")
                    time.sleep(wait_sec)
                else:
                    raise inner_e
    except Exception as e:
        print(f"  Gemini API error: {e}")
        return None


def extract_lead_sentences(body, rss_description):
    """AI 없이 기사 첫 2문장을 완결된 형태로 추출합니다 (폴백용)."""
    text = body if body else re.sub(r'<[^>]+>', '', rss_description).strip()
    sentences = [s.strip() for s in re.split(r'(?<=[.。]) +', text) if len(s.strip()) > 10]
    if not sentences:
        return text[:200]
    summary = sentences[0]
    if len(sentences) > 1:
        summary += " " + sentences[1]
    if len(summary) < 80 and len(sentences) > 2:
        summary += " " + sentences[2]
    return summary.strip()


def process_news():
    print("\n--- 채권/외환 뉴스 RSS 피드 수집 및 AI 요약 시작 ---")
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
    print(f"Found {len(items)} news articles. Processing with AI summarization...")

    for i, item in enumerate(items):
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

        # 1. 기사 본문 스크래핑 시도 (실패해도 계속 진행)
        print(f"  [{i+1}/{len(items)}] {title[:35]}...")
        body = scrape_article_body(link)

        # RSS description 정제 (HTML 태그 제거)
        clean_rss = re.sub(r'<[^>]+>', '', description).strip()

        # 2. Gemini AI 요약 (본문 OR RSS 발췌 사용)
        summary = ai_summarize(title, body, rss_desc=clean_rss)
        if not summary:
            # AI 폴백: 완결 문장 추출
            summary = extract_lead_sentences(body, description)

        # 분당 요청 제한 방지: 각 기사 처리 후 4초 대기
        time.sleep(4)

        news_obj = {
            "title": title.strip(),
            "link": link.strip(),
            "description": summary,
            "author": author.strip(),
            "date": display_date,
            "raw_date": pub_date,
            "ai_generated": gemini_client is not None  # 항상 AI 시도
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
        half = len(other_news) // 2
        daytime_news = other_news[:half]
        nighttime_news = other_news[half:]

    print(f"완료 - 주간: {len(daytime_news)}건, 야간: {len(nighttime_news)}건")

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
            ai_badge = '<span class="ai-badge">✨ AI 요약</span>' if news.get('ai_generated') else ''
            cards += f"""
            <a href="{news['link']}" target="_blank" class="news-card">
                <div class="news-meta">
                    <span class="news-date">🕒 {news['date']}</span>
                    <span class="news-author">✍️ {news['author']} {ai_badge}</span>
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

        .news-meta {{ display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-muted); font-weight: 500; flex-wrap: wrap; gap: 0.25rem; }}
        .news-title {{ font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin: 0; line-height: 1.4; }}
        .news-card:hover .news-title {{ color: #e2e8f0; }}

        .ai-badge {{
            background: linear-gradient(135deg, rgba(168,85,247,0.2), rgba(236,72,153,0.2));
            border: 1px solid rgba(168,85,247,0.3);
            color: #c084fc;
            padding: 0.1rem 0.5rem;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .news-desc-container {{
            background: rgba(0,0,0,0.2);
            padding: 1rem 1.2rem;
            border-radius: 8px;
            border-left: 3px solid rgba(99,102,241,0.3);
        }}
        .news-desc {{ font-size: 0.95rem; color: var(--text-secondary); margin: 0; line-height: 1.7; word-break: keep-all; }}

        .news-action {{ font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-top: 0.25rem; transition: color 0.2s; text-align: right; }}
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
                <p>연합인포맥스 주요 기사 · AI 핵심 요약</p>
            </div>
            <div class="update-badge">🔄 최종 업데이트: {update_time}</div>
        </header>

        <div class="news-grid">
            <div class="news-column col-day">
                <div class="column-header">
                    <span style="font-size:1.5rem;">☀️</span>
                    <span class="column-title">주간 주요 기사 (08:00 ~ 18:00)</span>
                </div>
                {daytime_html}
            </div>
            <div class="news-column col-night">
                <div class="column-header">
                    <span style="font-size:1.5rem;">🌙</span>
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
