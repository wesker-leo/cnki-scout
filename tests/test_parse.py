import unittest

from cnki_scout.crawl import Options, _matches
from cnki_scout.parse import parse_detail, parse_results, safe_cnki_url


RESULT_HTML = """
<table class="result-table-list"><tbody>
<tr><td class="name"><a href="/kcms2/article/abstract?v=123">示例论文甲</a></td>
<td class="author">张三; 李四</td><td class="source">示例期刊</td>
<td class="date">2024-05-01</td><td class="data">学术期刊</td>
<td class="quote"><a>1,234</a></td><td class="download">56</td></tr>
<tr><td class="name"><a href="javascript:alert(1)">不安全链接</a></td></tr>
</tbody></table>
"""

DETAIL_HTML = """
<html><head><meta name="citation_title" content="示例论文甲">
<meta name="citation_doi" content="doi:10.1234/test.2024.01"></head><body>
<div class="brief"><h1>示例论文甲</h1></div>
<span id="ChDivSummary">本文讨论示例问题。 更多</span>
<p class="keywords"><a>主题甲；</a><a>主题乙；</a></p>
<div class="docinfo"><p>作者单位： 某大学；某研究院</p><p>专辑：示例专辑</p>
<p>专题：示例专题</p><p>学科专业：示例学科</p><p>数据库：学术期刊</p></div>
</body></html>
"""


class ParserTests(unittest.TestCase):
    def test_result_fields_and_url_guard(self):
        rows = parse_results(RESULT_HTML, "https://kns.cnki.net/kns8s/defaultresult/index")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["citations"], 1234)
        self.assertEqual(rows[0]["downloads"], 56)
        self.assertEqual(rows[0]["database"], "学术期刊")
        self.assertTrue(rows[0]["url"].startswith("https://kns.cnki.net/kcms2/"))
        self.assertEqual(safe_cnki_url("https://example.com/a", "https://kns.cnki.net/"), "")

    def test_older_grid_layout_and_http_upgrade(self):
        html = """<div id="gridTable"><table><tr><th>题名</th></tr>
        <tr><td class="name"><a href="http://kns.cnki.net/kcms/detail/one">旧版文章</a></td>
        <td class="author">王五</td><td class="date">2021</td><td class="quote">0</td></tr>
        </table></div>"""
        rows = parse_results(html, "https://kns.cnki.net/")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://kns.cnki.net/kcms/detail/one")
        self.assertEqual(rows[0]["citations"], 0)

    def test_detail_fields(self):
        result = parse_detail(DETAIL_HTML)
        self.assertEqual(result["abstract"], "本文讨论示例问题。")
        self.assertEqual(result["keywords"], ["主题甲", "主题乙"])
        self.assertEqual(result["doi"], "10.1234/test.2024.01")
        self.assertEqual(result["institutions"], ["某大学", "某研究院"])
        self.assertEqual(result["discipline"], "示例学科")

    def test_filters_do_not_treat_unknown_as_zero(self):
        row = {"publication_date": "2024-05-01", "citations": None}
        self.assertFalse(_matches(row, Options("示例检索词", start_year=2023, min_citations=0)))
        row["citations"] = 3
        self.assertTrue(_matches(row, Options("示例检索词", start_year=2023, min_citations=2)))


if __name__ == "__main__":
    unittest.main()
