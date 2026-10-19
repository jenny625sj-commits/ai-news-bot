"""
AI 산업 뉴스(정책/규제, 기업/투자, 연구/기술, 보안, 제품/출시)를 영어권 매체 RSS에서
수집해서 data/ai_news/archive.json 에 계속 누적한다.

종목/주가 관련 기사(주가, 실적, 애널리스트 등급 등)는 제목 패턴으로 걸러내고,
이미 archive에 있는 기사(링크 기준, 또는 제목이 매우 유사한 경우)는 건너뛴다.

사용 예:
    python scripts/fetch_ai_industry_news.py
"""

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_common  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
ARCHIVE_PATH = ROOT / "data" / "ai_news" / "archive.json"
FETCH_WINDOW_DAYS = 4  # 이보다 오래된 기사는 애초에 후보에서 제외 (TOP7 선정은 rank 단계에서 48시간으로 더 좁힘)
DEDUPE_WINDOW_DAYS = 5  # 최근 며칠치 archive와만 제목 유사도 비교 (성능)

GOOGLE_NEWS_QUERY = (
    # -stock/-shares/-earnings를 구글 검색어에 직접 넣으면 "본문 어디에든 그 단어가 있으면
    # 통째로 제외"가 되어버려서, OpenAI 매출 전망 하향처럼 AI 업계에 실제로 중요하지만
    # 시장 반응("~ shares slide")이 같이 보도되는 뉴스까지 전부 빠지는 문제가 있었음.
    # 종목 스팸 제목은 STOCK_EXCLUDE_PATTERN(제목만 검사)로 거르는 걸로 충분하다.
    '(artificial intelligence OR "AI model" OR OpenAI OR Anthropic OR DeepMind OR '
    f'"AI regulation" OR "AI policy" OR "AI safety" OR chatbot) when:{FETCH_WINDOW_DAYS}d'
)
GOOGLE_NEWS_URL = (
    f"https://news.google.com/rss/search?q={quote(GOOGLE_NEWS_QUERY)}&hl=en-US&gl=US&ceid=US:en"
)

# dedicated=True 인 피드는 이미 AI 전용 카테고리라 AI_KEYWORD_PATTERN 필터를 건너뛴다.
FEEDS = [
    {"name": "Google News", "url": GOOGLE_NEWS_URL, "dedicated": False},
    {"name": "TechCrunch", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "dedicated": True},
    {"name": "Ars Technica", "url": "https://arstechnica.com/ai/feed/", "dedicated": True},
    {"name": "Wired", "url": "https://www.wired.com/feed/tag/ai/latest/rss", "dedicated": True},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "dedicated": True},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "dedicated": False},
]

AI_KEYWORD_PATTERN = re.compile(
    r"\b(ai|a\.i\.|artificial intelligence|machine learning|deep learning|neural network|"
    r"llm|large language model|genai|generative ai|chatgpt|gpt-?\d|openai|anthropic|claude|"
    r"gemini|deepmind|copilot|chatbot|agentic)\b",
    re.IGNORECASE,
)

CATEGORY_RULES = [
    ("정책·규제", re.compile(r"\b(regulat\w*|policy|law|lawsuit|antitrust|ban|legislat\w*|senate|congress|"
                             r"eu ai act|executive order|white house|president|election|government)\b", re.IGNORECASE)),
    ("보안", re.compile(r"\b(security|cyberattack|cyber attack|hack\w*|vulnerabilit\w*|breach|jailbreak|misuse|exploit)\b", re.IGNORECASE)),
    ("기업·투자", re.compile(r"\b(funding|raise[sd]?|valuation|acquir\w*|acquisition|partnership|invest\w*|ipo|merger|"
                             r"cloud deal|billion|deal with)\b", re.IGNORECASE)),
    ("제품·출시", re.compile(r"\b(launch\w*|releas\w*|unveil\w*|announc\w*|update[sd]?|rollout|available now|debut\w*)\b", re.IGNORECASE)),
    ("연구·기술", re.compile(r"\b(research|study|paper|benchmark|breakthrough|dataset|training|algorithm)\b", re.IGNORECASE)),
]


def guess_category(title: str) -> str:
    for label, pattern in CATEGORY_RULES:
        if pattern.search(title):
            return label
    return "기타"


def run() -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=FETCH_WINDOW_DAYS)

    archive = news_common.load_archive(ARCHIVE_PATH)
    existing_ids = {a["id"] for a in archive}
    dedupe_cutoff = now - timedelta(days=DEDUPE_WINDOW_DAYS)
    recent_titles = [
        news_common.normalize_title(a["title"]) for a in archive
        if datetime.fromisoformat(a["published_at"]) >= dedupe_cutoff
    ]

    new_articles = []
    fetched_count, skipped_stock, skipped_offtopic, skipped_old = 0, 0, 0, 0

    for feed in FEEDS:
        print(f"수집 중: {feed['name']} ...")
        try:
            raw_items = news_common.fetch_feed(feed["url"], feed["name"])
        except Exception as e:  # noqa: BLE001
            print(f"  실패: {e}")
            continue

        for raw in raw_items:
            fetched_count += 1
            title = raw["title"]
            if not title or len(title) < 5 or not raw["link"]:
                continue
            if raw["published_at"] < cutoff:
                skipped_old += 1
                continue
            if news_common.STOCK_EXCLUDE_PATTERN.search(title):
                skipped_stock += 1
                continue
            if not feed["dedicated"] and not AI_KEYWORD_PATTERN.search(title):
                skipped_offtopic += 1
                continue

            aid = news_common.article_id(raw["link"])
            if aid in existing_ids:
                continue
            if news_common.is_near_duplicate(title, recent_titles):
                continue

            article = {
                "id": aid,
                "title": title,
                "link": raw["link"],
                "source": raw["source"] or feed["name"],
                "published_at": raw["published_at"].isoformat(),
                "category": guess_category(title),
                "first_seen_at": now.isoformat(),
            }
            new_articles.append(article)
            existing_ids.add(aid)
            recent_titles.append(news_common.normalize_title(title))

    if new_articles:
        print(f"신규 기사 {len(new_articles)}건 한국어 제목 번역 중...")
        news_common.translate_titles(new_articles)

    archive.extend(new_articles)
    news_common.save_archive(ARCHIVE_PATH, archive)

    print(
        f"\n총 {fetched_count}건 확인 -> 신규 {len(new_articles)}건 추가 "
        f"(제외: 종목뉴스 {skipped_stock}, 주제무관 {skipped_offtopic}, 기간초과 {skipped_old}) "
        f"-> archive 누적 {len(archive)}건"
    )
    return {"new_count": len(new_articles), "archive_total": len(archive), "new_articles": new_articles}


if __name__ == "__main__":
    run()
