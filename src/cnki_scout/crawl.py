"""Sequential browser collection with explicit access limits and partial output."""

from __future__ import annotations

import json
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout, sync_playwright

from .export import write_readable_outputs
from .parse import parse_detail, parse_results


SEARCH_HOME = "https://kns.cnki.net/kns8s/"
RESULT_ROWS = ".result-table-list tbody tr, #gridTable table tr"
EMPTY_DETAILS = {
    "abstract": "", "keywords": [], "institutions": [], "doi": "", "collection": "",
    "topic": "", "discipline": "", "database_detail": "", "detail_title": "",
    "detail_authors": "", "detail_source": "", "detail_publication_date": "",
}


class CollectionStopped(RuntimeError):
    """Site verification, access refusal, or changed page structure stopped collection."""


@dataclass(frozen=True)
class Options:
    query: str
    max_results: int = 30
    max_pages: int = 10
    start_year: int | None = None
    end_year: int | None = None
    min_citations: int | None = None
    sort: str = "relevance"
    delay_min: float = 8.0
    delay_max: float = 15.0
    manual_search: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _blocked(page: Page, status: int | None = None) -> bool:
    if status in (403, 429, 503):
        return True
    url = page.url.lower()
    if "/verify/" in url or "captcha" in url or "/login" in url or "passport.cnki.net" in url:
        return True
    title = page.title().strip().lower()
    return any(word in title for word in ("安全验证", "人机验证", "访问受限", "用户登录", "captcha", "access denied"))


def _check_page(page: Page, status: int | None = None) -> None:
    if _blocked(page, status):
        raise CollectionStopped("知网要求验证或拒绝访问。已停止并保留已有结果；请在浏览器中手动处理，稍后再运行。")


def _first_visible(page: Page, selectors: tuple[str, ...]):
    for selector in selectors:
        loc = page.locator(selector).first
        try:
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _wait_results(page: Page) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        _check_page(page)
        if page.locator(RESULT_ROWS).count() > 0:
            return
        page.wait_for_timeout(500)
    raise CollectionStopped("未找到知网文献结果表。请检查登录、检索条件或页面选择器。")


def _find_results_page(context: BrowserContext, preferred: Page, previous_pages: set[Page] | None = None) -> Page:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        for candidate in (preferred, *[p for p in context.pages if p != preferred]):
            if candidate.is_closed():
                continue
            if previous_pages is not None and candidate != preferred and candidate in previous_pages:
                continue
            _check_page(candidate)
            try:
                if candidate.locator(RESULT_ROWS).count() > 0:
                    return candidate
            except Exception:
                continue
        preferred.wait_for_timeout(500)
    raise CollectionStopped("未找到知网文献结果表。请检查登录、检索条件或页面选择器。")


def _submit_search(context: BrowserContext, page: Page, query: str) -> Page:
    response = page.goto(SEARCH_HOME, wait_until="domcontentloaded", timeout=30_000)
    _check_page(page, response.status if response else None)
    field = _first_visible(page, ("#txt_search", "input.search-input", "#txt_SearchText", "textarea.search-input"))
    if field is None:
        raise CollectionStopped("没有找到检索框；可改用 --manual-search 在浏览器中手动检索。")
    field.fill(query)
    previous_pages = set(context.pages)
    button = _first_visible(page, (".search-tab-content.search-form.cur .search-btn", "input.search-btn", ".search-btn", "button.search-btn"))
    if button:
        button.click()
    else:
        field.press("Enter")
    results_page = _find_results_page(context, page, previous_pages)
    result_field = results_page.locator("#txt_search").first
    if result_field.count() and result_field.input_value().strip() != query.strip():
        raise CollectionStopped("结果页检索框与本次关键词不一致，已停止以免读取旧结果。")
    return results_page


def _sort(page: Page, sort: str) -> str:
    codes = {"relevance": "FFD", "time": "PT", "citations": "CF", "downloads": "DFR"}
    labels = {
        "relevance": ("相关度",),
        "time": ("发表时间", "时间"),
        "citations": ("被引量", "被引"),
        "downloads": ("下载量", "下载"),
    }[sort]
    code = codes[sort]
    current = page.locator(f"#orderList li[data-sort='{code}']").first
    if current.count() and current.is_visible():
        if "cur" not in (current.get_attribute("class") or "").split():
            before = page.locator(RESULT_ROWS).all_text_contents()
            grid_response = None
            try:
                with page.expect_response(lambda response: urlparse(response.url).path == "/kns8s/brief/grid", timeout=15_000) as pending:
                    current.click()
                grid_response = pending.value
                _check_page(page, grid_response.status)
            except PlaywrightTimeout:
                # Older CNKI pages may update the table without this endpoint.
                pass
            page.wait_for_function(
                "code => document.querySelector(`#orderList li[data-sort='${code}']`)?.classList.contains('cur')",
                arg=code,
                timeout=15_000,
            )
            try:
                page.wait_for_function(
                    "before => JSON.stringify(Array.from(document.querySelectorAll('.result-table-list tbody tr, #gridTable table tr')).map(row => row.textContent)) !== JSON.stringify(before)",
                    arg=before,
                    timeout=5_000,
                )
            except PlaywrightTimeout:
                if grid_response is None:
                    raise CollectionStopped("排序后没有收到新结果，已停止以免采集旧顺序。")
        _wait_results(page)
        return labels[-1]
    for label in labels:
        for selector in (f".sort-list a:text-is('{label}')", f".sort-list li:text-is('{label}')", f"a:text-is('{label}')"):
            loc = _first_visible(page, (selector,))
            if loc:
                loc.click()
                _wait_results(page)
                return label
    raise CollectionStopped(f"未找到“{sort}”排序按钮。可用 --manual-search 先在浏览器中设定排序。")


def _next_page(page: Page, previous_url: str) -> bool:
    next_link = _first_visible(page, ("#PageNext", "a[title='下一页']", ".page-next", "a:text-is('下一页')", "button:text-is('下一页')"))
    if next_link is None:
        return False
    classes = (next_link.get_attribute("class") or "").lower()
    if "disabled" in classes or next_link.get_attribute("aria-disabled") == "true":
        return False
    next_link.click()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        _check_page(page)
        rows = parse_results(page.content(), page.url)
        if rows and rows[0]["url"] != previous_url:
            return True
        page.wait_for_timeout(500)
    raise CollectionStopped("点击下一页后结果没有变化，已停止以免重复采集。")


def _filter_reason(row: dict, options: Options) -> str:
    if options.start_year is not None or options.end_year is not None:
        year = re.search(r"(?:19|20)\d{2}", row["publication_date"])
        if not year:
            return "发表年份缺失"
        value = int(year.group())
        if options.start_year is not None and value < options.start_year:
            return f"早于 {options.start_year} 年"
        if options.end_year is not None and value > options.end_year:
            return f"晚于 {options.end_year} 年"
    if options.min_citations is not None:
        if row["citations"] is None:
            return "被引数未显示"
        if row["citations"] < options.min_citations:
            return f"被引数低于 {options.min_citations}"
    return ""


def _matches(row: dict, options: Options) -> bool:
    return not _filter_reason(row, options)


class _Pacer:
    def __init__(self, lower: float, upper: float):
        self.lower, self.upper = lower, upper
        self.last = time.monotonic()

    def wait(self) -> None:
        target = self.last + random.uniform(self.lower, self.upper)
        remaining = target - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self.last = time.monotonic()


def login(profile: Path, channel: str | None = None) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        kwargs = {"user_data_dir": str(profile), "headless": False, "accept_downloads": False}
        if channel:
            kwargs["channel"] = channel
        context = pw.chromium.launch_persistent_context(**kwargs)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.cnki.net/", wait_until="domcontentloaded", timeout=30_000)
            if not sys.stdin.isatty():
                raise CollectionStopped("登录需要交互式终端。")
            input("请在浏览器里使用个人或机构账号登录知网；完成后按 Enter 保存本地浏览器会话…")
        finally:
            context.close()


def collect(options: Options, output_dir: Path, profile: Path, channel: str | None = None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    profile.mkdir(parents=True, exist_ok=True)
    (output_dir / "records.jsonl").touch()
    (output_dir / "errors.jsonl").touch()
    (output_dir / "candidate_rows.jsonl").touch()
    manifest = {
        "schema_version": 1,
        "source": "CNKI",
        "started_at": _now(),
        "query": options.query,
        "filters": asdict(options),
        "sort_applied": None,
        "site_query": None,
        "site_total_results": None,
        "status": "running",
        "pages_visited": 0,
        "rows_seen": 0,
        "records_saved": 0,
        "detail_errors": 0,
        "exclusion_counts": {},
        "message": "",
    }
    seen: set[tuple[str, str, str]] = set()
    pacer = _Pacer(options.delay_min, options.delay_max)
    try:
        with sync_playwright() as pw:
            kwargs = {"user_data_dir": str(profile), "headless": False, "accept_downloads": False}
            if channel:
                kwargs["channel"] = channel
            context = pw.chromium.launch_persistent_context(**kwargs)
            context.set_default_timeout(10_000)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                if options.manual_search:
                    page.goto("https://www.cnki.net/", wait_until="domcontentloaded", timeout=30_000)
                    if not sys.stdin.isatty():
                        raise CollectionStopped("--manual-search 需要交互式终端。")
                    input("请在浏览器中搜索并设置筛选/排序，停留在结果第一页，然后按 Enter 开始采集…")
                    page = _find_results_page(context, page)
                    manifest["sort_applied"] = "用户在网页手动设置"
                else:
                    page = _submit_search(context, page, options.query)
                    pacer.wait()
                    manifest["sort_applied"] = _sort(page, options.sort)
                search_field = page.locator("#txt_search").first
                manifest["site_query"] = search_field.input_value().strip() if search_field.count() else None
                total_match = re.search(r"共找到\s*([\d,]+)\s*条结果", page.locator("body").inner_text())
                manifest["site_total_results"] = int(total_match.group(1).replace(",", "")) if total_match else None
                detail_page = context.new_page()
                consecutive_bad_details = 0
                with (output_dir / "records.jsonl").open("w", encoding="utf-8") as records, (output_dir / "errors.jsonl").open("w", encoding="utf-8") as errors, (output_dir / "candidate_rows.jsonl").open("w", encoding="utf-8") as candidates:
                    for page_number in range(1, options.max_pages + 1):
                        _check_page(page)
                        rows = parse_results(page.content(), page.url)
                        if not rows:
                            raise CollectionStopped("结果页没有可解析的文献行，已停止。")
                        manifest["pages_visited"] = page_number
                        first_url = rows[0]["url"]
                        for position, row in enumerate(rows, start=1):
                            manifest["rows_seen"] += 1
                            key = tuple(re.sub(r"\s+", "", row[field]).casefold() for field in ("title", "authors", "source"))
                            reason = _filter_reason(row, options)
                            if key in seen:
                                reason = "重复结果"
                            else:
                                seen.add(key)
                            candidate = {**row, "result_page": page_number, "position_on_page": position, "decision": reason or "符合筛选条件"}
                            candidates.write(json.dumps(candidate, ensure_ascii=False) + "\n")
                            candidates.flush()
                            if reason:
                                counts = manifest["exclusion_counts"]
                                counts[reason] = counts.get(reason, 0) + 1
                                continue
                            pacer.wait()
                            row.update(EMPTY_DETAILS)
                            try:
                                response = detail_page.goto(row["url"], wait_until="domcontentloaded", timeout=30_000)
                                _check_page(detail_page, response.status if response else None)
                                if response and response.status >= 400:
                                    raise RuntimeError(f"详情页 HTTP {response.status}")
                                details = parse_detail(detail_page.content())
                                row.update(details)
                                row["authors"] = row["authors"] or details["detail_authors"]
                                row["source"] = row["source"] or details["detail_source"]
                                row["publication_date"] = row["publication_date"] or details["detail_publication_date"]
                                row["database"] = row["database"] or details["database_detail"]
                                row["detail_status"] = "ok" if details["abstract"] else "abstract_missing"
                                if any(details[field] for field in ("abstract", "detail_title", "keywords", "doi")):
                                    consecutive_bad_details = 0
                                else:
                                    consecutive_bad_details += 1
                            except CollectionStopped:
                                raise
                            except Exception as exc:
                                manifest["detail_errors"] += 1
                                consecutive_bad_details += 1
                                row["detail_status"] = "error"
                                errors.write(json.dumps({"url": row["url"], "error": str(exc)}, ensure_ascii=False) + "\n")
                                errors.flush()
                            row.update({"query": options.query, "result_page": page_number, "position_on_page": position, "collected_at": _now()})
                            records.write(json.dumps(row, ensure_ascii=False) + "\n")
                            records.flush()
                            manifest["records_saved"] += 1
                            print(f"[{manifest['records_saved']}/{options.max_results}] {row['title']}", flush=True)
                            if consecutive_bad_details >= 3:
                                raise CollectionStopped("连续 3 个详情页未获得有效元数据，可能是登录失效或页面改版；已停止。")
                            if manifest["records_saved"] >= options.max_results:
                                manifest["status"] = "limit_reached"
                                break
                        if manifest["status"] == "limit_reached":
                            break
                        if page_number == options.max_pages:
                            manifest["status"] = "page_limit_reached"
                            break
                        pacer.wait()
                        if not _next_page(page, first_url):
                            manifest["status"] = "no_more_pages"
                            break
            finally:
                context.close()
    except (CollectionStopped, PlaywrightTimeout) as exc:
        manifest["status"] = "stopped"
        manifest["message"] = str(exc)
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        manifest["message"] = "用户中断采集，已有结果已保留。"
    except Exception as exc:
        manifest["status"] = "error"
        manifest["message"] = f"{type(exc).__name__}: {exc}"
    finally:
        manifest["finished_at"] = _now()
        (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_readable_outputs(output_dir, manifest)
    return manifest
