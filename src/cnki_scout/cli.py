"""Command line interface."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from .crawl import Options, collect, login


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cnki-scout", description="限速采集知网文献元数据，保存为 UTF-8 JSONL")
    parser.add_argument("--profile", type=Path, default=Path(".browser_profile"), help="本机浏览器登录数据目录")
    parser.add_argument("--browser-channel", choices=("chrome", "msedge"), help="使用系统浏览器；默认使用 Playwright Chromium")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="打开浏览器，手动完成学校账号登录")
    run = sub.add_parser("collect", help="搜索、筛选并采集元数据")
    run.add_argument("query", help="检索关键词")
    run.add_argument("--max-results", type=int, default=30, help="最多保存几篇（1–200，默认 30）")
    run.add_argument("--max-pages", type=int, default=10, help="最多查看几页（1–50，默认 10）")
    run.add_argument("--start-year", type=int)
    run.add_argument("--end-year", type=int)
    run.add_argument("--min-citations", type=int, help="列表被引数低于此值的文章不进入详情页")
    run.add_argument("--sort", choices=("relevance", "time", "citations", "downloads"), default="relevance")
    run.add_argument("--delay-min", type=float, default=8.0, help="访问间隔下界（至少 5 秒）")
    run.add_argument("--delay-max", type=float, default=15.0, help="访问间隔上界")
    run.add_argument("--manual-search", action="store_true", help="手动完成搜索及网站筛选/排序后开始采集")
    run.add_argument("--output", type=Path, help="新输出目录；默认 output/时间-关键词")
    return parser


def _validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command != "collect":
        return
    if not 1 <= args.max_results <= 200:
        parser.error("--max-results 必须在 1 到 200 之间")
    if not 1 <= args.max_pages <= 50:
        parser.error("--max-pages 必须在 1 到 50 之间")
    if args.delay_min < 5 or args.delay_max < args.delay_min:
        parser.error("访问间隔要求 --delay-min >= 5 且 --delay-max >= --delay-min")
    if args.start_year and args.end_year and args.start_year > args.end_year:
        parser.error("起始年份不得晚于结束年份")
    if args.min_citations is not None and args.min_citations < 0:
        parser.error("--min-citations 不得小于 0")
    if args.output and args.output.exists():
        parser.error("输出目录已存在，请选择新目录，以免覆盖已有采集结果")


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    _validate(args, parser)
    if args.command == "login":
        login(args.profile, args.browser_channel)
        print(f"登录会话保存在 {args.profile.resolve()}")
        return
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", args.query).strip("-")[:30] or "query"
    output = args.output or Path("output") / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
    options = Options(
        query=args.query,
        max_results=args.max_results,
        max_pages=args.max_pages,
        start_year=args.start_year,
        end_year=args.end_year,
        min_citations=args.min_citations,
        sort=args.sort,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        manual_search=args.manual_search,
    )
    result = collect(options, output, args.profile, args.browser_channel)
    print(f"状态：{result['status']}；保存 {result['records_saved']} 篇；结果：{output.resolve()}")
    if result["message"]:
        print(result["message"])


if __name__ == "__main__":
    main()
