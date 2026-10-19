"""
data/bigtech_news/archive.json 을 읽어서 web/bigtech_news_dashboard.html 을
정적 HTML로 렌더링한다. TOP N 없이 최신 기사를 전부 날짜별로 보여준다.

사용 예:
    python scripts/build_bigtech_dashboard.py
"""

import sys
from datetime import date as date_cls, datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_common  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = ROOT / "data" / "bigtech_news" / "archive.json"
OUT_PATH = ROOT / "web" / "bigtech_news_dashboard.html"
KST = ZoneInfo("Asia/Seoul")

COMPANIES = ["Meta", "Microsoft", "Amazon", "Google", "Apple", "Tesla", "SpaceX", "Nvidia", "OpenAI", "Anthropic", "xAI"]

COMPANY_COLORS = {
    "Meta": "#0866ff", "Microsoft": "#00a4ef", "Amazon": "#ff9900", "Google": "#34a853",
    "Apple": "#555555", "Tesla": "#cc0000", "SpaceX": "#1e293b", "Nvidia": "#76b900",
    "OpenAI": "#10a37f", "Anthropic": "#d97757", "xAI": "#000000",
}

NEW_THRESHOLD_MINUTES = 90  # 1시간 주기 자동 갱신 + 약간의 여유 - 이보다 최근에 수집된 기사는 NEW 표시


def is_new(first_seen_at: str | None, now: datetime) -> bool:
    if not first_seen_at:
        return False
    minutes = (now - datetime.fromisoformat(first_seen_at)).total_seconds() / 60
    return 0 <= minutes <= NEW_THRESHOLD_MINUTES


def relative_time(iso_str: str, now: datetime) -> str:
    dt = datetime.fromisoformat(iso_str)
    diff = now - dt
    minutes = int(diff.total_seconds() // 60)
    if minutes < 1:
        return "방금"
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    days = hours // 24
    return f"{days}일 전"


def article_row(article: dict, now: datetime) -> str:
    company = article["company"]
    title_ko = article.get("title_ko")
    title_en = article["title"]
    link = escape(article["link"], quote=True)

    if title_ko:
        titles_html = (
            f'<a class="archive-title-ko" href="{link}" target="_blank" rel="noopener">{escape(title_ko)}</a>'
            f'<span class="archive-title-en">{escape(title_en)}</span>'
        )
    else:
        titles_html = f'<a class="archive-title-ko" href="{link}" target="_blank" rel="noopener">{escape(title_en)}</a>'

    new_badge = '<span class="new-badge">NEW</span>' if is_new(article.get("first_seen_at"), now) else ""

    return (
        f'<div class="archive-row" data-company="{escape(company)}" data-title="{escape(title_en.lower())}">'
        f'<span class="company-tag" data-company="{escape(company)}">{escape(company)}</span>{new_badge}'
        f'<div class="archive-titles">{titles_html}</div>'
        f'<span class="archive-source">{escape(article["source"])}</span>'
        f'<span class="archive-time">{relative_time(article["published_at"], now)}</span>'
        f'</div>'
    )


def group_by_kst_date(archive: list) -> dict:
    groups: dict[str, list] = {}
    for a in archive:
        d = datetime.fromisoformat(a["published_at"]).astimezone(KST).date().isoformat()
        groups.setdefault(d, []).append(a)
    return dict(sorted(groups.items(), reverse=True))


def date_label(date_str: str, today_str: str) -> str:
    if date_str == today_str:
        return f"{date_str} (오늘)"
    d = date_cls.fromisoformat(date_str)
    t = date_cls.fromisoformat(today_str)
    if (t - d).days == 1:
        return f"{date_str} (어제)"
    return date_str


def run() -> Path:
    archive = news_common.load_archive(ARCHIVE_PATH)
    now = datetime.now(timezone.utc)
    now_kst = now.astimezone(KST)

    grouped = group_by_kst_date(archive)
    today_str = now_kst.date().isoformat()
    day_html_parts = []
    for date_str, articles in grouped.items():
        articles_sorted = sorted(articles, key=lambda a: a["published_at"], reverse=True)
        rows = "\n      ".join(article_row(a, now) for a in articles_sorted)
        day_html_parts.append(f"""  <div class="archive-day">
    <h3>{date_label(date_str, today_str)} · {len(articles_sorted)}건</h3>
    <div class="archive-list">
      {rows}
    </div>
  </div>""")
    day_html = "\n".join(day_html_parts) if day_html_parts else '<p class="footer-note">아직 수집된 기사가 없습니다.</p>'

    generated_label = now_kst.strftime("%Y-%m-%d %H:%M KST")
    chips_html = "\n    ".join(
        f'<span class="chip-filter" data-company="{escape(c)}">{escape(c)}</span>' for c in COMPANIES
    )
    color_css = "\n".join(
        f'.company-tag[data-company="{c}"] {{ background: {col}22; color: {col}; }}'
        for c, col in COMPANY_COLORS.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>빅테크 뉴스 대시보드</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #f7f7f8;
  --panel: #ffffff;
  --border: #ddd;
  --text: #1a1a1a;
  --muted: #777;
  --accent: #2563eb;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }}
.topbar {{ display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; background: var(--panel); border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 8px; }}
.topbar h1 {{ font-size: 19px; margin: 0; }}
.muted {{ color: var(--muted); font-size: 12px; }}
.topbar-right {{ display: flex; align-items: center; gap: 10px; }}
.refresh-btn {{ display: inline-flex; align-items: center; gap: 5px; padding: 5px 11px; border-radius: 6px; border: 1px solid var(--border); background: var(--panel); color: var(--text); font-size: 12px; cursor: pointer; }}
.refresh-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
.page-tabs {{ display: flex; gap: 4px; padding: 8px 20px 0; background: var(--panel); }}
.page-tab {{ padding: 8px 14px; font-size: 13px; text-decoration: none; color: var(--muted); border-bottom: 2px solid transparent; }}
.page-tab.active {{ color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }}
.disclaimer {{ margin: 0; padding: 6px 20px; font-size: 12px; color: var(--muted); background: #fafafa; border-bottom: 1px solid var(--border); }}

.controls {{ display: flex; align-items: center; gap: 10px; padding: 12px 20px; flex-wrap: wrap; }}
.chip-filter {{ display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--panel); font-size: 13px; cursor: pointer; }}
.chip-filter.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
#search-input {{ margin-left: auto; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; min-width: 200px; }}

.section-title {{ font-size: 14px; font-weight: 600; margin: 20px 20px 8px; color: var(--muted); text-transform: uppercase; letter-spacing: .03em; }}

.company-tag {{ display: inline-block; flex-shrink: 0; font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #eef2ff; color: var(--accent); font-weight: 600; }}
.new-badge {{ display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: #ef4444; color: white; margin-left: 4px; vertical-align: middle; }}
{color_css}

.archive-day {{ padding: 0 20px; margin-bottom: 18px; }}
.archive-day h3 {{ font-size: 13px; color: var(--muted); margin: 0 0 8px; font-weight: 600; }}
.archive-list {{ display: flex; flex-direction: column; gap: 6px; }}
.archive-row {{ display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }}
.archive-titles {{ flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
.archive-title-ko {{ color: inherit; text-decoration: none; font-weight: 500; }}
.archive-title-ko:hover {{ color: var(--accent); }}
.archive-title-en {{ color: var(--muted); font-size: 11px; line-height: 1.3; }}
.archive-row .company-tag {{ margin-top: 1px; }}
.archive-row .archive-source {{ color: var(--muted); font-size: 11px; flex-shrink: 0; margin-top: 1px; }}
.archive-row .archive-time {{ color: var(--muted); font-size: 11px; flex-shrink: 0; margin-top: 1px; }}

.footer-note {{ padding: 20px; font-size: 12px; color: var(--muted); }}
</style>
</head>
<body>
  <header class="topbar">
    <h1>🏢 빅테크 뉴스</h1>
    <div class="topbar-right">
      <span id="generated-at" class="muted">마지막 업데이트: {generated_label} · 누적 기사 {len(archive)}건</span>
      <button class="refresh-btn" onclick="location.reload()" title="이 파일을 다시 불러옵니다 (2분마다 자동으로도 실행됨)">🔄 새로고침</button>
    </div>
  </header>

  <nav class="page-tabs">
    <a class="page-tab" href="ai_news_dashboard.html">AI 산업 뉴스</a>
    <a class="page-tab active" href="bigtech_news_dashboard.html">빅테크</a>
  </nav>

  <p class="disclaimer">
    ※ META, Microsoft, Amazon, Google, Apple, Tesla, SpaceX, Nvidia, OpenAI, Anthropic, xAI 관련 최신 뉴스를
    개수 제한 없이 모읍니다 (종목/주가 관련 기사는 제외). 바탕화면 바로가기를 실행할 때마다 최신 기사로 갱신됩니다 —
    서버 없이 이 HTML 파일 자체로 동작하며, 기사를 클릭하면 원문으로 이동합니다. 새로고침 버튼은 이 파일을 다시
    불러올 뿐 새 기사를 가져오진 않습니다 (탭을 열어두면 2분마다 자동 새로고침됩니다).
  </p>

  <div class="controls">
    <span class="chip-filter active" data-company="">전체</span>
    {chips_html}
    <input id="search-input" type="text" placeholder="키워드 검색" />
  </div>

  <div class="section-title">최신 뉴스</div>
{day_html}

  <p class="footer-note">
    scripts/run_bigtech_news_pipeline.py 를 다시 실행하면 최신 기사가 반영됩니다. (바탕화면 바로가기로 자동 실행)
  </p>

<script>
const chips = document.querySelectorAll(".chip-filter");
const searchInput = document.getElementById("search-input");
let activeCompany = "";

function applyFilter() {{
  const q = searchInput.value.trim().toLowerCase();
  document.querySelectorAll(".archive-row").forEach((row) => {{
    const matchesCompany = !activeCompany || row.dataset.company === activeCompany;
    const matchesQuery = !q || row.dataset.title.includes(q);
    row.style.display = (matchesCompany && matchesQuery) ? "" : "none";
  }});
  document.querySelectorAll(".archive-day").forEach((day) => {{
    const visible = [...day.querySelectorAll(".archive-row")].some((r) => r.style.display !== "none");
    day.style.display = visible ? "" : "none";
  }});
}}

chips.forEach((chip) => {{
  chip.addEventListener("click", () => {{
    chips.forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    activeCompany = chip.dataset.company;
    applyFilter();
  }});
}});
searchInput.addEventListener("input", applyFilter);

// 탭을 열어둔 동안 2분마다 자동 새로고침 (파일이 백그라운드에서 갱신됐으면 자동 반영)
setInterval(() => location.reload(), 120000);
</script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"대시보드 생성 완료 -> {OUT_PATH}")
    return OUT_PATH


if __name__ == "__main__":
    run()
