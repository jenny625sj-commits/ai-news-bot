"""
AI 산업 뉴스 + 빅테크 뉴스 파이프라인 실행 후, 이번 실행에서 새로 들어온 기사만
텔레그램으로 보낸다 (중복 발송 없음 - fetch 단계에서 이미 "신규"로 걸러진 것만 받음).

.env 에 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없으면 조용히 건너뛴다.

사용 예 (run_all_news.py에서 호출):
    notify_telegram.run(ai_fetch_result, bigtech_fetch_result)
"""

import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_common  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TOP7_PATH = ROOT / "data" / "ai_news" / "top7.json"

BIGTECH_PER_COMPANY_CAP = 5
AI_DASHBOARD_URL = "https://jenny625sj-commits.github.io/ai-news-bot/web/ai_news_dashboard.html"
BIGTECH_DASHBOARD_URL = "https://jenny625sj-commits.github.io/ai-news-bot/web/bigtech_news_dashboard.html"


def _article_line(article: dict) -> str:
    title = article.get("title_ko") or article["title"]
    link = escape(article["link"], quote=True)
    return f'• <a href="{link}">{escape(title)}</a>'


def notify_ai_news(ai_result: dict) -> None:
    """새 기사가 있을 때만, 이번에 다시 선정된 TOP7을 보낸다 (개별 기사 전부 보내면 스팸이 됨)."""
    new_articles = ai_result.get("new_articles") or []
    if not new_articles or not TOP7_PATH.exists():
        return
    top7 = json.loads(TOP7_PATH.read_text(encoding="utf-8"))
    items = top7.get("items") or []
    if not items:
        return

    lines = [f"🤖 <b>AI 산업 뉴스</b> (신규 {len(new_articles)}건 반영)", ""]
    for item in items:
        title = item.get("title_ko") or item["title_en"]
        link = escape(item["link"], quote=True)
        category = escape(item.get("category", ""))
        lines.append(f'• [{category}] <a href="{link}">{escape(title)}</a>')
    lines.append("")
    lines.append(f'📊 <a href="{AI_DASHBOARD_URL}">대시보드 전체 보기</a>')

    if news_common.send_telegram_message("\n".join(lines)):
        print("텔레그램 전송: AI 산업 뉴스")


def notify_bigtech_news(bigtech_result: dict) -> None:
    """신규 기사를 회사별로 묶어서 보낸다 (회사당 최대 5건, 나머지는 건수만 표기)."""
    new_articles = bigtech_result.get("new_articles") or []
    if not new_articles:
        return

    by_company: dict[str, list] = {}
    for a in new_articles:
        by_company.setdefault(a["company"], []).append(a)

    lines = [f"🏢 <b>빅테크 뉴스</b> (신규 {len(new_articles)}건)", ""]
    for company, articles in by_company.items():
        articles.sort(key=lambda a: a["published_at"], reverse=True)
        lines.append(f"<b>{escape(company)}</b> ({len(articles)}건)")
        for a in articles[:BIGTECH_PER_COMPANY_CAP]:
            lines.append(_article_line(a))
        remaining = len(articles) - BIGTECH_PER_COMPANY_CAP
        if remaining > 0:
            lines.append(f"  …외 {remaining}건 (대시보드에서 확인)")
        lines.append("")
    lines.append(f'📊 <a href="{BIGTECH_DASHBOARD_URL}">대시보드 전체 보기</a>')

    if news_common.send_telegram_message("\n".join(lines)):
        print("텔레그램 전송: 빅테크 뉴스")


def run(ai_result: dict, bigtech_result: dict) -> None:
    notify_ai_news(ai_result)
    notify_bigtech_news(bigtech_result)
