"""
빅테크 뉴스 파이프라인을 한 번에 실행한다: 수집(+누적) -> 대시보드 렌더링.
(TOP N 선정 없이 최신 기사를 전부 보여주므로 rank 단계는 없음)

사용 예:
    python scripts/run_bigtech_news_pipeline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bigtech_dashboard  # noqa: E402
import fetch_bigtech_news  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def run() -> dict:
    fetch_result = fetch_bigtech_news.run()
    dashboard_path = build_bigtech_dashboard.run()
    return {"fetch_result": fetch_result, "dashboard_path": dashboard_path}


if __name__ == "__main__":
    run()
