"""
AI 산업 뉴스 파이프라인을 한 번에 실행한다: 수집(+누적) -> TOP7 선정/번역 -> 대시보드 렌더링.

사용 예:
    python scripts/run_ai_news_pipeline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_ai_news_dashboard  # noqa: E402
import fetch_ai_industry_news  # noqa: E402
import rank_ai_news  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def run() -> dict:
    fetch_result = fetch_ai_industry_news.run()
    rank_ai_news.run()
    dashboard_path = build_ai_news_dashboard.run()
    return {"fetch_result": fetch_result, "dashboard_path": dashboard_path}


if __name__ == "__main__":
    run()
