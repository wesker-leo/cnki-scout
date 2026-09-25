"""Turn the machine-readable JSONL into files people can inspect easily."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path


DISPLAY_FIELDS = (
    ("title", "题名"),
    ("authors", "作者"),
    ("institutions", "作者单位"),
    ("source", "来源"),
    ("publication_date", "发表时间"),
    ("database", "数据库"),
    ("citations", "被引"),
    ("downloads", "下载"),
    ("abstract", "摘要"),
    ("keywords", "关键词"),
    ("collection", "专辑"),
    ("topic", "专题"),
    ("doi", "DOI"),
    ("discipline", "学科专业"),
    ("url", "知网链接"),
    ("detail_status", "详情状态"),
    ("result_page", "结果页"),
    ("position_on_page", "页内序号"),
    ("collected_at", "采集时间"),
)

CANDIDATE_FIELDS = (
    ("title", "题名"),
    ("authors", "作者"),
    ("source", "来源"),
    ("publication_date", "发表时间"),
    ("database", "数据库"),
    ("citations", "被引"),
    ("downloads", "下载"),
    ("result_page", "结果页"),
    ("position_on_page", "页内序号"),
    ("decision", "筛选判定"),
    ("url", "知网链接"),
)


def _value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(str(item) for item in value)
    return str(value)


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_readable_outputs(output_dir: Path, manifest: dict) -> None:
    """Write CSV with stable headers and a prose-oriented Markdown review file."""
    records = _read_records(output_dir / "records.jsonl")
    csv_path = output_dir / "records.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[label for _, label in DISPLAY_FIELDS])
        writer.writeheader()
        for record in records:
            writer.writerow({label: _value(record.get(key)) for key, label in DISPLAY_FIELDS})

    candidate_path = output_dir / "candidate_rows.jsonl"
    if candidate_path.exists():
        candidates = _read_records(candidate_path)
        with (output_dir / "search_results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=[label for _, label in CANDIDATE_FIELDS])
            writer.writeheader()
            for candidate in candidates:
                writer.writerow({label: _value(candidate.get(key)) for key, label in CANDIDATE_FIELDS})

    filters = manifest.get("filters", {})
    years = f"{filters.get('start_year') or '不限'}–{filters.get('end_year') or '不限'}"
    minimum = filters.get("min_citations")
    minimum_text = "不限" if minimum is None else str(minimum)
    lines = [
        "# CNKI 文献初筛结果",
        "",
        f"检索词：{html.escape(str(manifest.get('query', '')))}  ",
        f"发表年份：{years}；最低被引：{minimum_text}；排序：{html.escape(str(manifest.get('sort_applied') or filters.get('sort') or '未知'))}  ",
        f"保存篇数：{len(records)}；状态：{html.escape(str(manifest.get('status', '未知')))}",
        "",
    ]
    if candidate_path.exists():
        site_total = manifest.get("site_total_results")
        site_total_text = f"知网显示 **{site_total}** 条；" if site_total is not None else ""
        lines.extend((
            f"{site_total_text}程序扫描 **{manifest.get('rows_seen', 0)}** 条；本地筛选后保存 **{len(records)}** 篇。"
            "每条结果的保留或排除原因见 `search_results.csv`。",
            "",
        ))
    if not records:
        lines.extend(("当前条件下没有保存文献，因此没有逐篇字段。`records.csv` 保留了字段列名；可适当降低最低被引数后重新运行。", ""))
    for index, record in enumerate(records, start=1):
        lines.extend((f"## {index}. {html.escape(_value(record.get('title')))}", ""))
        for key, label in DISPLAY_FIELDS:
            if key in ("title", "abstract", "keywords", "url", "result_page", "position_on_page", "collected_at"):
                continue
            lines.append(f"- **{label}：** {html.escape(_value(record.get(key))) or '未提供'}")
        lines.extend(("", "### 摘要", "", html.escape(_value(record.get("abstract"))) or "未提供", ""))
        lines.append(f"**关键词：** {html.escape(_value(record.get('keywords'))) or '未提供'}")
        url = _value(record.get("url"))
        if url:
            lines.append(f"**知网详情：** [打开文献页面](<{url}>)")
        lines.append("")
    (output_dir / "records.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
