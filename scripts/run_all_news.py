"""
바탕화면 바로가기에서 호출하는 통합 진입점: AI 산업 뉴스 + 빅테크 뉴스
두 대시보드를 한 번에 갱신하고, 신규 기사가 있으면 텔레그램으로도 보낸다
(.env 에 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 없으면 알림은 조용히 건너뜀).

사용 예:
    python scripts/run_all_news.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notify_telegram  # noqa: E402
import run_ai_news_pipeline  # noqa: E402
import run_bigtech_news_pipeline  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def run() -> None:
    print("=== AI 산업 뉴스 ===")
    ai_out = run_ai_news_pipeline.run()
    print("\n=== 빅테크 뉴스 ===")
    bigtech_out = run_bigtech_news_pipeline.run()

    print("\n=== 텔레그램 알림 ===")
    notify_telegram.run(ai_out["fetch_result"], bigtech_out["fetch_result"])


if __name__ == "__main__":
    run()
