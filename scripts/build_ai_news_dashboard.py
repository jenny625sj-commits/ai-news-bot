"""
data/ai_news/archive.json + top7.json 을 읽어서 web/ai_news_dashboard.html
을 정적 HTML로 렌더링한다. 서버 없이 파일 자체로 동작한다.

사용 예:
    python scripts/build_ai_news_dashboard.py
"""

import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = ROOT / "data" / "ai_news" / "archive.json"
TOP7_PATH = ROOT / "data" / "ai_news" / "top7.json"
OUT_PATH = ROOT / "web" / "ai_news_dashboard.html"
KST = ZoneInfo("Asia/Seoul")

CATEGORIES = ["정책·규제", "기업·투자", "연구·기술", "보안", "제품·출시", "기타"]


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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


def article_card(item: dict, now: datetime, top: bool) -> str:
    title_ko = item.get("title_ko")
    title_en = item["title_en"] if "title_en" in item else item["title"]
    link = escape(item["link"], quote=True)
    category = item.get("category", "기타")
    source = escape(item["source"])
    rel_time = relative_time(item["published_at"], now)

    title_ko_html = f'<div class="article-title-ko">{escape(title_ko)}</div>' if title_ko else ""
    title_en_html = f'<div class="article-title-en">{escape(title_en)}</div>'
    if not title_ko:
        title_en_html = f'<div class="article-title-ko">{escape(title_en)}</div>'

    css_class = "article-card top" if top else "article-card"
    return f"""    <div class="{css_class}">
      <a href="{link}" target="_blank" rel="noopener">
        <span class="cat-tag" data-cat="{escape(category)}">{escape(category)}</span>
        {title_ko_html}
        {title_en_html}
      </a>
      <div class="article-meta"><span>{source}</span><span>{rel_time}</span></div>
    </div>"""


def archive_row(article: dict, now: datetime) -> str:
    title_ko = article.get("title_ko")
    title_en = article["title"]
    category = article.get("category", "기타")
    link = escape(article["link"], quote=True)

    if title_ko:
        titles_html = (
            f'<a class="archive-title-ko" href="{link}" target="_blank" rel="noopener">{escape(title_ko)}</a>'
            f'<span class="archive-title-en">{escape(title_en)}</span>'
        )
    else:
        titles_html = f'<a class="archive-title-ko" href="{link}" target="_blank" rel="noopener">{escape(title_en)}</a>'

    return (
        f'<div class="archive-row" data-cat="{escape(category)}" data-title="{escape(title_en.lower())}">'
        f'<span class="cat-tag" data-cat="{escape(category)}">{escape(category)}</span>'
        f'<div class="archive-titles">{titles_html}</div>'
        f'<span class="archive-source">{escape(article["source"])}</span>'
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
    from datetime import date as date_cls
    d = date_cls.fromisoformat(date_str)
    t = date_cls.fromisoformat(today_str)
    if (t - d).days == 1:
        return f"{date_str} (어제)"
    return date_str


def run() -> Path:
    archive = load_json(ARCHIVE_PATH, [])
    top7 = load_json(TOP7_PATH, {"generated_at": None, "items": []})
    now = datetime.now(timezone.utc)
    now_kst = now.astimezone(KST)

    top_ids = {item["link"] for item in top7["items"]}
    top_html = "\n".join(article_card(item, now, top=True) for item in top7["items"])
    if not top_html:
        top_html = '<p class="footer-note">아직 선정된 TOP 뉴스가 없습니다.</p>'

    grouped = group_by_kst_date(archive)
    today_str = now_kst.date().isoformat()
    archive_html_parts = []
    for date_str, articles in grouped.items():
        articles_sorted = sorted(articles, key=lambda a: a["published_at"], reverse=True)
        rows = "\n      ".join(archive_row(a, now) for a in articles_sorted)
        archive_html_parts.append(f"""  <div class="archive-day">
    <h3>{date_label(date_str, today_str)} · {len(articles_sorted)}건</h3>
    <div class="archive-list">
      {rows}
    </div>
  </div>""")
    archive_html = "\n".join(archive_html_parts) if archive_html_parts else '<p class="footer-note">아직 수집된 기사가 없습니다.</p>'

    generated_label = now_kst.strftime("%Y-%m-%d %H:%M KST")
    chips_html = "\n    ".join(
        f'<span class="chip-filter" data-cat="{escape(c)}">{escape(c)}</span>' for c in CATEGORIES
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>AI 산업 뉴스 대시보드</title>
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

.top-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; padding: 0 20px; }}
.article-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 6px; }}
.article-card.top {{ border-left: 3px solid var(--accent); }}
.cat-tag {{ display: inline-block; align-self: flex-start; font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #eef2ff; color: var(--accent); font-weight: 600; }}
.cat-tag[data-cat="보안"] {{ background: #fee2e2; color: #b91c1c; }}
.cat-tag[data-cat="기업·투자"] {{ background: #dcfce7; color: #15803d; }}
.cat-tag[data-cat="제품·출시"] {{ background: #ffedd5; color: #c2410c; }}
.cat-tag[data-cat="연구·기술"] {{ background: #ede9fe; color: #6d28d9; }}
.cat-tag[data-cat="기타"] {{ background: #f1f5f9; color: #64748b; }}
.article-title-ko {{ font-size: 14px; font-weight: 600; line-height: 1.4; }}
.article-title-en {{ font-size: 12px; color: var(--muted); line-height: 1.3; }}
.article-meta {{ font-size: 11px; color: var(--muted); display: flex; gap: 8px; margin-top: auto; }}
.article-card a {{ text-decoration: none; color: inherit; }}
.article-card a:hover .article-title-ko {{ color: var(--accent); }}

.archive-day {{ padding: 0 20px; margin-bottom: 18px; }}
.archive-day h3 {{ font-size: 13px; color: var(--muted); margin: 0 0 8px; font-weight: 600; }}
.archive-list {{ display: flex; flex-direction: column; gap: 6px; }}
.archive-row {{ display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }}
.archive-row .cat-tag {{ flex-shrink: 0; margin-top: 1px; }}
.archive-titles {{ flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }}
.archive-title-ko {{ color: inherit; text-decoration: none; font-weight: 500; }}
.archive-title-ko:hover {{ color: var(--accent); }}
.archive-title-en {{ color: var(--muted); font-size: 11px; line-height: 1.3; }}
.archive-row .archive-source {{ color: var(--muted); font-size: 11px; flex-shrink: 0; margin-top: 1px; }}

.footer-note {{ padding: 20px; font-size: 12px; color: var(--muted); }}
</style>
</head>
<body>
  <header class="topbar">
    <h1>🤖 AI 산업 뉴스</h1>
    <div class="topbar-right">
      <span id="generated-at" class="muted">마지막 업데이트: {generated_label} · 누적 기사 {len(archive)}건</span>
      <button class="refresh-btn" onclick="location.reload()" title="이 파일을 다시 불러옵니다 (2분마다 자동으로도 실행됨)">🔄 새로고침</button>
    </div>
  </header>

  <nav class="page-tabs">
    <a class="page-tab active" href="ai_news_dashboard.html">AI 산업 뉴스</a>
    <a class="page-tab" href="bigtech_news_dashboard.html">빅테크</a>
  </nav>

  <p class="disclaimer">
    ※ 종목/주가 관련 뉴스는 제외하고, AI 산업 자체(정책·규제, 기업·투자, 연구·기술, 보안, 제품 출시)에 관한 기사만 모읍니다.
    바탕화면 바로가기를 실행할 때마다 최신 기사를 새로 가져와 이 파일을 갱신합니다 — 서버 없이 이 HTML 파일 자체로 동작합니다.
    기사를 클릭하면 원문으로 이동합니다. 새로고침 버튼은 이 파일을 다시 불러올 뿐 새 기사를 가져오진 않습니다 -
    새 기사를 받으려면 바탕화면 바로가기를 다시 실행하세요 (탭을 열어두면 2분마다 자동 새로고침됩니다).
  </p>

  <div class="controls">
    <span class="chip-filter active" data-cat="">전체</span>
    {chips_html}
    <input id="search-input" type="text" placeholder="키워드 검색 (예: Anthropic, 규제)" />
  </div>

  <div class="section-title">오늘의 핵심 뉴스 TOP 7</div>
  <div class="top-grid">
{top_html}
  </div>

  <div class="section-title">누적 아카이브</div>
{archive_html}

  <p class="footer-note">
    scripts/run_ai_news_pipeline.py 를 다시 실행하면 최신 기사가 반영됩니다. (바탕화면 바로가기로 자동 실행)
  </p>

<script>
const chips = document.querySelectorAll(".chip-filter");
const searchInput = document.getElementById("search-input");
let activeCat = "";

function applyFilter() {{
  const q = searchInput.value.trim().toLowerCase();
  document.querySelectorAll(".archive-row").forEach((row) => {{
    const matchesCat = !activeCat || row.dataset.cat === activeCat;
    const matchesQuery = !q || row.dataset.title.includes(q);
    row.style.display = (matchesCat && matchesQuery) ? "" : "none";
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
    activeCat = chip.dataset.cat;
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
