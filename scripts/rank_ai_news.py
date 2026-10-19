"""
data/ai_news/archive.json 에서 최근 48시간 이내 기사 중 AI 산업에 가장 중요한
7개를 골라 한국어 제목으로 번역하고 카테고리를 매긴다.

하이브리드 방식 (top_ai_news.py와 동일한 패턴):
  - .env 에 ANTHROPIC_API_KEY가 있으면 Claude Haiku로 중요도 선정 + 번역 + 카테고리 재분류.
  - 키가 없거나 호출이 실패하면 출처 신뢰도 + 최신순으로 정렬한 폴백으로 자동 전환
    (번역 없이 원문 제목 그대로, 비용 0).

사용 예:
    python scripts/rank_ai_news.py
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ARCHIVE_PATH = ROOT / "data" / "ai_news" / "archive.json"
TOP7_PATH = ROOT / "data" / "ai_news" / "top7.json"

MODEL = "claude-haiku-4-5-20251001"
TOP_N = 7
# 예전엔 40으로 잘라서 보냈는데, 기사가 많은 날(하루 150~200건)은 recency 정렬 특성상
# 조금 더 오래됐을 뿐인 대형 뉴스(여러 매체가 동시에 보도한 이슈)가 윈도우 밖으로 밀려나
# TOP7 후보에서 통째로 빠지는 문제가 있었음. Haiku 컨텍스트/비용엔 거의 영향 없으니
# 넉넉하게 올려서 48시간 이내 기사는 왠만하면 전부 LLM이 직접 보고 판단하게 한다.
MAX_CANDIDATES_FOR_PROMPT = 150
MAX_AGE_HOURS = 48

CATEGORIES = ["정책·규제", "기업·투자", "연구·기술", "보안", "제품·출시", "기타"]

# 출처 신뢰도 가중치 (폴백 정렬에만 사용) - 높을수록 우선
SOURCE_TIER = {
    "Reuters": 3, "The New York Times": 3, "Bloomberg": 3, "The Wall Street Journal": 3,
    "Associated Press": 3, "AP": 3, "The Washington Post": 3, "Financial Times": 3,
    "TechCrunch": 2, "The Verge": 2, "Wired": 2, "Ars Technica": 2, "MIT Technology Review": 2,
}


def load_archive() -> list:
    if not ARCHIVE_PATH.exists():
        return []
    return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))


def recent_candidates(archive: list) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    candidates = [a for a in archive if datetime.fromisoformat(a["published_at"]) >= cutoff]
    candidates.sort(key=lambda a: a["published_at"], reverse=True)
    return candidates


def _article_ref(a: dict, title_ko: str | None = None, category: str | None = None) -> dict:
    return {
        "title_ko": title_ko,
        "title_en": a["title"],
        "link": a["link"],
        "source": a["source"],
        "published_at": a["published_at"],
        "category": category or a.get("category", "기타"),
    }


def extractive_top(candidates: list) -> list:
    ranked = sorted(candidates, key=lambda a: SOURCE_TIER.get(a["source"], 1), reverse=True)
    return [_article_ref(a) for a in ranked[:TOP_N]]


def _extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"응답에서 JSON을 찾지 못함: {text[:200]}")
    return json.loads(match.group(0))


def llm_top(client, candidates: list) -> list:
    subset = candidates[:MAX_CANDIDATES_FOR_PROMPT]
    numbered = "\n".join(f"{i+1}. {a['title']} - {a['source']}" for i, a in enumerate(subset))
    categories_str = ", ".join(CATEGORIES)
    prompt = f"""다음은 최근 48시간 동안 수집된 AI 산업 관련 해외 뉴스 후보 목록이다 (번호. 제목 - 매체).
"OOO 주가 2% 상승" 식의 단순 종목 시세 기사는 이미 제외된 상태이지만, 주요 AI 기업의
재무 상태 변화(매출 전망 하향/상향, 투자 유치 등)가 시장 전체에 충격을 준 경우처럼
AI 산업 자체에 중요한 사건이라면 제목에 "주가/stocks/market" 같은 단어가 있어도
정상적으로 포함된 것이니 걸러낼 필요 없다 - 오히려 이런 사건은 적극적으로 고려하라.

{numbered}

먼저 목록을 훑어서, 서로 다른 매체가 제목은 다르게 썼지만 같은 사건/발표를 다루고 있는
경우가 있는지 확인하라 (예: "OpenAI가 300여개 수학 문제를 풀었다고 발표" 같은 사건을
NYT/가디언/이코노미스트가 각자 다른 제목으로 보도하는 식). 여러 매체가 동시에 다룬 사건은
단독 보도 1건보다 화제성/중요도가 훨씬 높다는 뜻이니 TOP7 선정에서 강하게 우대하라.

이 중에서 AI 산업 전체에 미치는 영향이 크거나(정책/규제, 대형 딜/투자, 주요 기업의 재무/매출
전망 변경처럼 시장 전체가 반응한 사건, 안전/보안 사고, 중요한 연구 성과, 주요 제품 출시 등)
화제성이 높은 뉴스를 정확히 {TOP_N}개 선정하라.
같은 사건을 다루는 기사가 여러 개면 그중 가장 신뢰도 높은 매체 기사 하나만 선택하라.
각 기사에 대해 자연스러운 한국어 뉴스 제목으로 번역하고, 아래 카테고리 중 하나를 배정하라:
{categories_str}

아래 JSON 형식으로만 응답하라. 다른 텍스트는 출력하지 마라.

{{"items": [{{"index": 3, "title_ko": "번역된 제목", "category": "정책·규제"}}]}}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _extract_json(resp.content[0].text)

    items = []
    for it in data.get("items", []):
        idx = it.get("index")
        title_ko = (it.get("title_ko") or "").strip()
        category = it.get("category") if it.get("category") in CATEGORIES else None
        if not isinstance(idx, int) or not (1 <= idx <= len(subset)) or not title_ko:
            continue
        items.append(_article_ref(subset[idx - 1], title_ko, category))
    if not items:
        raise ValueError("LLM 응답에 유효한 항목이 없음")
    return items[:TOP_N]


def run() -> dict:
    archive = load_archive()
    candidates = recent_candidates(archive)
    print(f"최근 {MAX_AGE_HOURS}시간 이내 후보 {len(candidates)}건")

    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "method": "none", "items": []}
    if not candidates:
        print("후보 기사가 없어 TOP7을 생성하지 않음")
    else:
        client = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)

        if client is not None:
            try:
                result["items"] = llm_top(client, candidates)
                result["method"] = "llm"
            except Exception as e:  # noqa: BLE001
                print(f"LLM 선정 실패, 추출 방식으로 폴백: {e}")

        if not result["items"]:
            result["items"] = extractive_top(candidates)
            result["method"] = "extractive"

    TOP7_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOP7_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TOP{TOP_N} 뉴스({result['method']}) -> {TOP7_PATH}")
    return result


if __name__ == "__main__":
    run()
