import csv
import json
import tempfile
import unittest
from pathlib import Path

from cnki_scout.export import write_readable_outputs


class ExportTests(unittest.TestCase):
    def test_csv_and_markdown_show_article_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            record = {
                "title": "示例论文甲", "authors": "张三", "institutions": ["某大学"],
                "publication_date": "2024-05-01", "citations": 4, "downloads": 80,
                "abstract": "这是可供初筛的摘要。", "keywords": ["主题甲", "主题乙"],
                "doi": "10.1234/demo", "url": "https://kns.cnki.net/example",
            }
            (folder / "records.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            candidates = [
                {**record, "decision": "符合筛选条件", "result_page": 1, "position_on_page": 1},
                {**record, "title": "较早文献", "decision": "早于 2022 年", "result_page": 1, "position_on_page": 2},
            ]
            (folder / "candidate_rows.jsonl").write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in candidates) + "\n", encoding="utf-8"
            )
            write_readable_outputs(folder, {"query": "示例检索词", "filters": {"start_year": 2022, "end_year": 2026}, "status": "limit_reached", "rows_seen": 2, "site_total_results": 2})
            with (folder / "records.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["题名"], "示例论文甲")
            self.assertEqual(rows[0]["作者单位"], "某大学")
            self.assertEqual(rows[0]["摘要"], "这是可供初筛的摘要。")
            markdown = (folder / "records.md").read_text(encoding="utf-8")
            self.assertIn("### 摘要", markdown)
            self.assertIn("**关键词：** 主题甲；主题乙", markdown)
            self.assertIn("知网显示 **2** 条", markdown)
            with (folder / "search_results.csv").open(encoding="utf-8-sig", newline="") as stream:
                candidates_csv = list(csv.DictReader(stream))
            self.assertEqual(len(candidates_csv), 2)
            self.assertEqual(candidates_csv[1]["筛选判定"], "早于 2022 年")

    def test_empty_result_still_has_visible_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "records.jsonl").touch()
            write_readable_outputs(folder, {"query": "示例检索词", "filters": {"min_citations": 5}, "status": "no_more_pages"})
            with (folder / "records.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows), 1)
            self.assertIn("摘要", rows[0])
            self.assertIn("没有保存文献", (folder / "records.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
