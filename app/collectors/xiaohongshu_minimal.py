from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

DEFAULT_SEARCH_DIR = Path.home() / ".xiaohongshu-cli" / "search_results"

SORT_LABELS = {
    "general": "\u7efc\u5408",
    "latest": "\u6700\u65b0",
    "time_descending": "\u6700\u65b0",
    "popularity_descending": "\u6700\u591a\u70b9\u8d5e",
    "likes_descending": "\u6700\u591a\u70b9\u8d5e",
    "comments_descending": "\u6700\u591a\u8bc4\u8bba",
    "collects_descending": "\u6700\u591a\u6536\u85cf",
}

TIME_FILTER_LABELS = {
    "": "",
    "all": "\u4e0d\u9650",
    "day": "\u4e00\u5929\u5185",
    "week": "\u4e00\u5468\u5185",
    "month": "\u4e00\u6708\u5185",
    "half_year": "\u534a\u5e74\u5185",
}

FILTER_TRIGGER_TEXT = ("\u7b5b\u9009", "\u5df2\u7b5b\u9009")
SORT_SECTION_LABEL = "\u6392\u5e8f\u4f9d\u636e"
TIME_SECTION_LABEL = "\u53d1\u5e03\u65f6\u95f4"


def build_search_url(keyword: str) -> str:
    encoded = quote(keyword or "")
    return f"https://www.xiaohongshu.com/search_result?keyword={encoded}&source=web_explore_feed"


def resolve_sort_label(sort: str | None) -> str:
    if not sort:
        return SORT_LABELS["popularity_descending"]
    return SORT_LABELS.get(sort, sort)


def resolve_time_label(time_filter: str | None) -> str:
    if not time_filter:
        return ""
    return TIME_FILTER_LABELS.get(time_filter, time_filter)


async def collect_xiaohongshu(
    keyword: str,
    *,
    sort: str = "popularity_descending",
    time_filter: str = "",
    limit: int = 20,
    output_dir: str | Path = DEFAULT_SEARCH_DIR,
    headless: bool | None = None,
) -> list[dict]:
    """Collect Xiaohongshu search results with the smallest useful Playwright flow.

    Set XHS_USER_DATA_DIR to reuse an already logged-in Chromium profile.
    """

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Playwright is required: pip install playwright && playwright install chromium") from exc

    limit = max(1, int(limit or 20))
    if headless is None:
        headless = os.getenv("XHS_HEADLESS", "0") == "1"

    async with async_playwright() as playwright:
        user_data_dir = os.getenv("XHS_USER_DATA_DIR")
        browser = None
        if user_data_dir:
            context = await playwright.chromium.launch_persistent_context(user_data_dir, headless=headless)
        else:
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context()

        page = await context.new_page()
        try:
            await page.goto(build_search_url(keyword), wait_until="domcontentloaded")
            await page.wait_for_timeout(1200)
            await apply_filters(page, sort=sort, time_filter=time_filter)
            await scroll_for_results(page, limit)
            raw_items = await extract_state_items(page)
            if not raw_items:
                raw_items = await extract_dom_items(page)
            items = normalize_feed_items(raw_items, limit=limit)
            write_results(items, keyword, output_dir)
            return items
        finally:
            await context.close()
            if browser:
                await browser.close()


async def apply_filters(page, *, sort: str = "popularity_descending", time_filter: str = "") -> None:
    sort_label = resolve_sort_label(sort)
    time_label = resolve_time_label(time_filter)
    if not sort_label and not time_label:
        return

    opened = await open_filter_panel(page)
    if not opened:
        return
    if sort_label:
        await click_filter_tag(page, SORT_SECTION_LABEL, sort_label)
    if time_label:
        await click_filter_tag(page, TIME_SECTION_LABEL, time_label)
    await page.wait_for_timeout(1000)


async def open_filter_panel(page) -> bool:
    script = r"""
    (labels) => {
      const visible = (el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      for (const el of document.querySelectorAll('button, div, span')) {
        const text = (el.textContent || '').trim();
        if (labels.some(label => text.includes(label)) && visible(el) && el.getAttribute('aria-hidden') !== 'true') {
          el.click();
          return true;
        }
      }
      return false;
    }
    """
    return bool(await page.evaluate(script, list(FILTER_TRIGGER_TEXT)))


async def click_filter_tag(page, section_label: str, option_label: str) -> bool:
    script = r"""
    ({ sectionLabel, optionLabel }) => {
      const visible = (el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const sections = Array.from(document.querySelectorAll('.filters, [class*=filter], section, div'));
      const section = sections.find(el => (el.textContent || '').includes(sectionLabel) && visible(el));
      const root = section || document;
      const tags = Array.from(root.querySelectorAll('.tags, [class*=tag], button, span, div'));
      const target = tags.find(el =>
        (el.textContent || '').trim() === optionLabel &&
        el.getAttribute('aria-hidden') !== 'true' &&
        visible(el)
      );
      if (!target) return false;
      target.click();
      return true;
    }
    """
    return bool(await page.evaluate(script, {"sectionLabel": section_label, "optionLabel": option_label}))


async def scroll_for_results(page, limit: int) -> None:
    rounds = min(12, max(2, (limit // 6) + 2))
    for _ in range(rounds):
        count = await page.evaluate("document.querySelectorAll('section.note-item, a[href*=\"/explore/\"], a[href*=\"/search_result/\"]').length")
        if count >= limit:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(900)


async def extract_state_items(page) -> list[dict]:
    script = r"""
    () => {
      const feeds = window.__INITIAL_STATE__?.search?.feeds?._value || [];
      return feeds
        .filter(item => item && item.noteCard)
        .map(item => ({
          id: item.id || '',
          xsecToken: item.xsecToken || '',
          title: item.noteCard?.displayTitle || '',
          author: item.noteCard?.user?.nickname || item.noteCard?.user?.nickName || '',
          liked_count: item.noteCard?.interactInfo?.likedCount ?? '',
          collected_count: item.noteCard?.interactInfo?.collectedCount ?? '',
          comment_count: item.noteCard?.interactInfo?.commentCount ?? '',
          type: item.noteCard?.type || '',
        }));
    }
    """
    rows = await page.evaluate(script)
    return rows if isinstance(rows, list) else []


async def extract_dom_items(page) -> list[dict]:
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const rows = [];
      const seen = new Set();
      const cards = document.querySelectorAll('section.note-item, section:has(a[href*="/explore/"]), section:has(a[href*="/search_result/"])');
      for (const el of cards) {
        const link = el.querySelector('a[href*="/explore/"], a[href*="/search_result/"]');
        const href = link?.getAttribute('href') || '';
        if (!href || seen.has(href)) continue;
        seen.add(href);
        rows.push({
          title: clean(el.querySelector('.title, .note-title, a.title')?.textContent || link.textContent || ''),
          author: clean(el.querySelector('.author-name, .nick-name, .name')?.textContent || ''),
          liked_count: clean(el.querySelector('.count, .like-count, .like-wrapper .count')?.textContent || ''),
          url: href.startsWith('http') ? href : 'https://www.xiaohongshu.com' + href,
        });
      }
      return rows;
    }
    """
    rows = await page.evaluate(script)
    return rows if isinstance(rows, list) else []


def normalize_feed_items(raw_items: list[dict], *, limit: int = 20) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = normalize_item(raw)
        key = item.get("id") or item.get("url") or item.get("title")
        if not key or key in seen or not item.get("title"):
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= limit:
            break
    return items


def normalize_item(raw: dict) -> dict:
    note_id = str(raw.get("id") or raw.get("note_id") or "").strip()
    token = str(raw.get("xsecToken") or raw.get("xsec_token") or "").strip()
    url = str(raw.get("url") or raw.get("link") or "").strip()
    if not url and note_id and token:
        url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_search"
    return {
        "id": note_id or _id_from_url(url),
        "title": str(raw.get("title") or raw.get("note_title") or "").strip(),
        "author": str(raw.get("author") or raw.get("nickname") or "").strip(),
        "liked_count": raw.get("liked_count") or raw.get("likes") or "",
        "collected_count": raw.get("collected_count") or raw.get("collects") or "",
        "comment_count": raw.get("comment_count") or raw.get("comments") or "",
        "content_type": raw.get("content_type") or raw.get("type") or "",
        "url": url,
    }


def write_results(items: list[dict], keyword: str, output_dir: str | Path = DEFAULT_SEARCH_DIR) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_keyword = re.sub(r"[^\w\-]+", "_", keyword, flags=re.UNICODE).strip("_") or "search"
    path = directory / f"search_{safe_keyword}_deep_{stamp}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _id_from_url(url: str) -> str:
    match = re.search(r"/(?:explore|search_result|note)/([0-9a-f]{24})", url, re.I)
    return match.group(1) if match else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Xiaohongshu search collector")
    parser.add_argument("--keyword", default="pet")
    parser.add_argument("--sort", default="popularity_descending")
    parser.add_argument("--time-filter", default="")
    parser.add_argument("--limit", "--deep-limit", dest="limit", type=int, default=20)
    parser.add_argument("--output-dir", default=str(DEFAULT_SEARCH_DIR))
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    items = asyncio.run(
        collect_xiaohongshu(
            args.keyword,
            sort=args.sort,
            time_filter=args.time_filter,
            limit=args.limit,
            output_dir=args.output_dir,
            headless=args.headless,
        )
    )
    print(json.dumps({"count": len(items)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

