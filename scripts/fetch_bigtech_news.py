"""
빅테크 기업(META, Microsoft, Amazon, Google, Apple, Tesla, SpaceX, Nvidia, OpenAI, Anthropic)
관련 최신 뉴스를 회사별 Google News RSS 검색으로 수집해서 data/bigtech_news/archive.json 에
계속 누적한다. TOP N 선정 없이 최신 기사를 모두 모아서 보여주는 용도.

OpenAI/Anthropic은 Google News 검색 외에 자체 블로그/사이트 글도 "extra_feeds"로
같이 수집한다 (OpenAI는 공식 RSS, Anthropic은 RSS가 없어서 site: 검색으로 대체).

종목/주가 관련 기사(주가, 실적, 애널리스트 등급 등)는 제목 패턴으로 걸러내고,
이미 archive에 있는 기사(링크 기준, 또는 제목이 매우 유사한 경우)는 건너뛴다.

사용 예:
    python scripts/fetch_bigtech_news.py
"""

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
ARCHIVE_PATH = ROOT / "data" / "bigtech_news" / "archive.json"
FETCH_WINDOW_DAYS = 4
DEDUPE_WINDOW_DAYS = 5


def _google_news_url(query: str) -> str:
    # when:Nd 를 넣어야 Google이 관련도순이 아니라 최근 N일 이내로 결과를 좁혀준다
    # (없으면 관련도순이라 100개 결과 중 상당수가 window 밖의 오래된 기사로 채워짐).
    return f"https://news.google.com/rss/search?q={quote(f'{query} when:{FETCH_WINDOW_DAYS}d')}&hl=en-US&gl=US&ceid=US:en"


# 회사명만으로는 다른 뜻과 섞일 수 있어(Apple=과일, Tesla=과학자, Amazon=열대우림 등)
# "회사명 (관련 브랜드/인물 키워드 OR ...)" 형태로 두 조건을 AND로 묶어 오탐을 줄인다.
# extra_feeds: 회사 공식 블로그/사이트 글을 Google News 검색과 별개로 직접 수집.
COMPANIES = [
    {
        "name": "Meta",
        "query": 'Meta (Zuckerberg OR Instagram OR WhatsApp OR "Meta AI" OR "Meta Platforms" OR "Ray-Ban Meta")',
    },
    {
        "name": "Microsoft",
        "query": 'Microsoft (Nadella OR Azure OR Xbox OR Copilot OR Windows OR OpenAI OR "Microsoft Corp")',
        "extra_feeds": [{"label": "Microsoft Blog", "url": "https://blogs.microsoft.com/feed/"}],
    },
    {
        "name": "Amazon",
        "query": 'Amazon (Bezos OR Jassy OR AWS OR Prime OR Alexa OR "Amazon Web Services")',
        "extra_feeds": [{"label": "AWS Blog", "url": "https://aws.amazon.com/blogs/aws/feed/"}],
    },
    {
        "name": "Google",
        "query": 'Google (Alphabet OR "Sundar Pichai" OR "Google Cloud" OR Gemini OR "Google DeepMind" OR YouTube OR Pixel OR Waymo OR antitrust)',
        "extra_feeds": [{"label": "Google Blog", "url": "https://blog.google/rss/"}],
    },
    {"name": "Apple", "query": 'Apple (iPhone OR "Tim Cook" OR "Apple Inc" OR iOS OR MacBook OR "App Store" OR "Apple Watch" OR "Apple TV")'},
    {"name": "Tesla", "query": 'Tesla (Musk OR "Model Y" OR "Model 3" OR Cybertruck OR Autopilot OR "Full Self-Driving" OR Robotaxi OR Gigafactory)'},
    {"name": "SpaceX", "query": 'SpaceX (Starship OR Starlink OR "Elon Musk" OR "Falcon 9" OR NASA OR rocket OR launch)'},
    {"name": "Nvidia", "query": 'Nvidia (Huang OR GeForce OR CUDA OR Blackwell OR GPU OR chip OR AI)'},
    # xAI(Grok 개발사)는 머스크가 만든 별도 법인 - SpaceX 소속이 아니라 독립 회사라서 분리.
    # 공식 RSS가 없고 site: 검색도 노이즈가 많아(문서 페이지 위주) extra_feeds는 생략.
    {"name": "xAI", "query": 'xAI (Grok OR "Elon Musk" OR "x.ai")'},
    {
        "name": "OpenAI",
        "query": 'OpenAI (ChatGPT OR "Sam Altman" OR GPT OR "Sora" OR "Dall-E")',
        "extra_feeds": [{"label": "OpenAI Blog", "url": "https://openai.com/news/rss.xml"}],
    },
    {
        "name": "Anthropic",
        "query": 'Anthropic (Claude OR "Dario Amodei" OR "Claude Code")',
        # Anthropic은 공식 RSS가 없어서 Google News의 site: 검색으로 자사 블로그 글을 잡는다.
        "extra_feeds": [{"label": "Anthropic Site", "url": _google_news_url("site:anthropic.com")}],
    },
]


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
    fetched_count, skipped_stock, skipped_old = 0, 0, 0

    for company in COMPANIES:
        print(f"수집 중: {company['name']} ...")
        # company['query']가 이미 자체 괄호 그룹("Meta (Zuckerberg OR ...)")이라 여기서 또
        # 괄호로 감싸면(이중 중첩) 일부 회사(Meta/Amazon/Google)에서 when: 필터와 충돌해
        # Google이 결과를 0건 반환하는 현상이 있었음 -> 감싸지 않고 그대로 이어붙인다.
        # -stock/-shares/-earnings는 Google 검색어에 넣지 않는다 - 본문 어디에든 그 단어가
        # 있으면 통째로 제외되어서, 회사에 실제로 중요한데 시장 반응("~ shares fall")이
        # 같이 보도되는 뉴스까지 빠지는 문제가 있었음 (제목 기준 STOCK_EXCLUDE_PATTERN으로 충분).
        sources = [{"label": "Google News", "url": _google_news_url(company["query"])}]
        sources.extend(company.get("extra_feeds", []))

        for source in sources:
            print(f"  - {source['label']} ...")
            try:
                raw_items = news_common.fetch_feed(source["url"], source["label"])
            except Exception as e:  # noqa: BLE001
                print(f"    실패: {e}")
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

                aid = news_common.article_id(raw["link"])
                if aid in existing_ids:
                    continue
                if news_common.is_near_duplicate(title, recent_titles):
                    continue

                article = {
                    "id": aid,
                    "title": title,
                    "link": raw["link"],
                    "source": raw["source"] or source["label"],
                    "company": company["name"],
                    "published_at": raw["published_at"].isoformat(),
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
        f"(제외: 종목뉴스 {skipped_stock}, 기간초과 {skipped_old}) "
        f"-> archive 누적 {len(archive)}건"
    )
    return {"new_count": len(new_articles), "archive_total": len(archive), "new_articles": new_articles}


if __name__ == "__main__":
    run()
