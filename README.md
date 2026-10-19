# AI News Bot

AI 산업 뉴스(비종목) + 빅테크(META/MS/Amazon/Google/Apple/Tesla/SpaceX/Nvidia/OpenAI/Anthropic/xAI)
뉴스를 1시간마다 수집해서 정적 대시보드를 갱신하고, 새 기사가 있으면 텔레그램으로 보내는 자동화.

GitHub Actions가 매시간 `scripts/run_all_news.py`를 실행하고, 바뀐 `data/`, `web/` 파일을
이 레포에 다시 커밋한다 (서버 없이 "크론 커밋" 방식으로 상태를 유지).

## 로컬에서 실행

```
pip install -r requirements.txt
cp .env.example .env   # 값 채워넣기
python scripts/run_all_news.py
```

## 필요한 환경변수 (.env 또는 GitHub Secrets)

- `ANTHROPIC_API_KEY` — TOP7 선정 + 한국어 번역
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — 새 기사 텔레그램 알림

## 대시보드

`web/ai_news_dashboard.html`, `web/bigtech_news_dashboard.html` — 서버 없이 파일 자체로 동작.
