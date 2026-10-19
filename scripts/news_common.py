"""
뉴스 대시보드 파이프라인(AI 산업 뉴스, 빅테크 뉴스 등)에서 공통으로 쓰는
RSS/Atom 피드 파싱, 중복 제거, 아카이브 저장 유틸리티.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

TRANSLATE_MODEL = "claude-haiku-4-5-20251001"
TRANSLATE_BATCH_SIZE = 40

TELEGRAM_MAX_LEN = 3500  # Telegram 메시지 한도(4096자)보다 여유있게 잡아서 끊어 보냄

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REQUEST_TIMEOUT = 15
TITLE_SIMILARITY_THRESHOLD = 0.82

STOCK_EXCLUDE_PATTERN = re.compile(
    r"\b(stock price|shares? (rose|fell|jumped|dropped|gained|surged|plunged)|price target|"
    r"buy rating|sell rating|hold rating|analyst (upgrade|downgrade)|"
    r"earnings (call|report|beat|miss)|quarterly (earnings|results)|eps of|"
    r"nasdaq:|nyse:|52-week|market cap|dividend|stock split|shares outstanding|"
    r"q[1-4] 20\d\d results|price prediction)\b",
    re.IGNORECASE,
)


def article_id(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def is_near_duplicate(title: str, recent_titles: list, threshold: float = TITLE_SIMILARITY_THRESHOLD) -> bool:
    norm = normalize_title(title)
    for other in recent_titles:
        if SequenceMatcher(None, norm, other).ratio() >= threshold:
            return True
    return False


def load_archive(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_archive(path: Path, articles: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    articles.sort(key=lambda a: a["published_at"], reverse=True)
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_rss_pubdate(text: str):
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_atom_updated(text: str):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _clean_title(title: str, source: str | None) -> str:
    if source and title.endswith(f" - {source}"):
        return title[: -(len(source) + 3)].strip()
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", title).strip()


def parse_feed(xml_bytes: bytes, feed_name: str) -> list:
    """RSS 2.0 / Atom 피드를 [{title, link, source, published_at(datetime, UTC)}] 로 파싱."""
    root = ET.fromstring(xml_bytes)
    items = []

    if root.tag.endswith("}feed") or root.tag == "feed":  # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title_el = entry.find("a:title", ns)
            link_el = entry.find("a:link[@rel='alternate']", ns)
            if link_el is None:
                link_el = entry.find("a:link", ns)
            updated_el = entry.find("a:updated", ns)
            if updated_el is None:
                updated_el = entry.find("a:published", ns)
            if title_el is None or link_el is None or updated_el is None:
                continue
            published_at = _parse_atom_updated(updated_el.text or "")
            if published_at is None:
                continue
            items.append({
                "title": (title_el.text or "").strip(),
                "link": link_el.get("href", ""),
                "source": feed_name,
                "published_at": published_at,
            })
    else:  # RSS 2.0
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")
            source_el = item.find("source")
            if title_el is None or link_el is None or pubdate_el is None:
                continue
            published_at = _parse_rss_pubdate(pubdate_el.text or "")
            if published_at is None:
                continue
            source_name = (source_el.text or "").strip() if source_el is not None else feed_name
            items.append({
                "title": _clean_title((title_el.text or "").strip(), source_name),
                "link": (link_el.text or "").strip(),
                "source": source_name,
                "published_at": published_at,
            })
    return items


def fetch_feed(url: str, feed_name: str) -> list:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return parse_feed(resp.content, feed_name)


def extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"응답에서 JSON을 찾지 못함: {text[:200]}")
    return json.loads(match.group(0))


def translate_titles(articles: list, batch_size: int = TRANSLATE_BATCH_SIZE) -> None:
    """articles(각 dict에 'title' 키 필요)에 'title_ko' 키를 채워 넣는다 (in-place).
    .env 에 ANTHROPIC_API_KEY가 없거나 호출이 실패하면 조용히 건너뛴다
    (title_ko가 없으면 대시보드에서 영어 제목 그대로 노출됨)."""
    if not articles:
        return
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    for i in range(0, len(articles), batch_size):
        chunk = articles[i:i + batch_size]
        numbered = "\n".join(f"{j + 1}. {a['title']}" for j, a in enumerate(chunk))
        prompt = f"""다음은 영어 뉴스 제목 목록이다 (번호. 제목).
각 제목을 자연스러운 한국어 뉴스 제목체로 번역하라. 회사명/인물명 등 고유명사는 그대로 유지하고,
과도한 의역 없이 원문 의미를 보존하라.

{numbered}

아래 JSON 형식으로만 응답하라. 다른 텍스트는 출력하지 마라.
{{"items": [{{"index": 1, "title_ko": "번역된 제목"}}]}}"""
        try:
            resp = client.messages.create(
                model=TRANSLATE_MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            data = extract_json(resp.content[0].text)
            for it in data.get("items", []):
                idx = it.get("index")
                title_ko = (it.get("title_ko") or "").strip()
                if isinstance(idx, int) and 1 <= idx <= len(chunk) and title_ko:
                    chunk[idx - 1]["title_ko"] = title_ko
        except Exception as e:  # noqa: BLE001
            print(f"  번역 실패(배치 {i // batch_size + 1}): {e}")


def _chunk_text(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list:
    """긴 메시지를 줄 단위로 끊어서 max_len 이하 조각들로 나눈다."""
    if len(text) <= max_len:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def send_telegram_message(text: str) -> bool:
    """TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID(.env)로 메시지를 보낸다.
    .env에 설정이 없으면 조용히 건너뛴다(False 반환). 길면 여러 메시지로 나눠 보낸다."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    ok = True
    for chunk in _chunk_text(text):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if not resp.ok:
                print(f"  텔레그램 전송 실패: {resp.status_code} {resp.text[:200]}")
                ok = False
        except Exception as e:  # noqa: BLE001
            print(f"  텔레그램 전송 실패: {e}")
            ok = False
    return ok
