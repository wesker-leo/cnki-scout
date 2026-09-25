# CNKI Scout：知网文献初筛采集器

[中文](README.md) · [English](README.en.md)

CNKI Scout 使用可见浏览器会话，按关键词检索中国知网（CNKI）文献，顺序读取结果列表与文献详情页，并导出适合人工和 AI 初筛的元数据。它采集题名、作者、作者单位、来源、发表时间、数据库、被引、下载、摘要、关键词、专辑、专题、DOI、学科专业等**页面可见字段**。本项目不下载论文全文，也不隶属于中国知网。

## 功能

- 关键词检索；按知网页面的相关度、发表时间、被引或下载排序。
- 本地筛选发表年份和最低被引数；自动翻页，设置最多保存篇数与最多扫描页数。
- 逐篇读取详情页；保留知网页面全部已扫描结果及每条结果的筛选原因，方便核对数量。
- 输出 JSONL、CSV 和 Markdown；运行中断时保留已写入的数据。
- 单浏览器会话、顺序访问、随机间隔；遇到访问限制或人机验证即停止。

## 安装

需要 Python 3.10+，以及可访问知网的网络环境或可用账号（个人账号、机构账号均可）。以下命令适用于 macOS/Linux：

```bash
git clone https://github.com/wesker-leo/cnki-scout.git
cd cnki-scout
python3.12 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m playwright install chromium
```

如果本机已经安装 Chrome，可跳过最后一步，并在下方命令的 `cnki-scout` 后、子命令前加 `--browser-channel chrome`。Windows 请将 `.venv/bin/` 换成 `.venv\Scripts\`，用 `py -3.12 -m venv .venv` 创建环境。

## 登录与运行

先在弹出的浏览器里**手动**登录知网个人账号或机构账号，回到终端按 Enter：

```bash
.venv/bin/cnki-scout login
```

将下例中的 `检索词` 换成你自己的关键词。下例保留指定年份且被引至少 3 次的文献，按被引排序：

```bash
.venv/bin/cnki-scout collect "检索词" \
  --start-year 2022 --end-year 2026 \
  --min-citations 3 --sort citations \
  --max-results 30 --max-pages 8
```

其他筛选方式：

```bash
# 只按年份筛选，按相关度排序
.venv/bin/cnki-scout collect "检索词" --start-year 2022 --end-year 2026 --sort relevance --max-results 30

# 不限年份与被引数，按下载排序
.venv/bin/cnki-scout collect "检索词" --sort downloads --max-results 50 --max-pages 8

# 在知网中手动设置检索条件与排序，再让程序采集
.venv/bin/cnki-scout collect "检索词" --manual-search --max-results 30
```

`--sort` 支持 `relevance`、`time`、`citations`、`downloads`。排序由知网页面执行；年份和最低被引数由程序在列表采集后本地筛选，因此**知网页面显示的命中数可能大于最终保存篇数**。启用年份筛选时，缺少年份的结果会被排除；只要设置了 `--min-citations`，未显示被引数的结果也会被排除，**包括设置为 `0` 时**。完全不按被引数筛选时，请省略该参数。

## 输出文件

每次运行会新建 `output/<时间>-<检索词>/`：

| 文件 | 用途 |
| --- | --- |
| `records.md` | 按篇阅读题名、作者、单位、摘要、关键词等 |
| `records.csv` | 带中文列名的表格，可用 Excel 打开 |
| `records.jsonl` | 每行一篇，供 AI 或脚本读取；未知数字为 `null` |
| `search_results.csv` | 知网页面已扫描的列表行，以及逐条筛选原因 |
| `candidate_rows.jsonl` | 上述列表行的机器可读版本 |
| `manifest.json` | 检索词、知网页面结果数、扫描数、保存数、参数及停止原因 |
| `errors.jsonl` | 个别详情页读取失败的记录 |

例如知网显示多条结果、最终只保存其中一部分时，可以打开 `search_results.csv` 核对其余结果是因年份、被引数缺失还是重复而未进入 `records`。摘要是适切度初筛的主要依据；被引和作者单位可作辅助信息，不应单独视为论文质量评分。

## 访问节奏与限制

默认相邻访问间隔 8–15 秒，允许的最小间隔为 5 秒；一次最多保存 200 篇、扫描 50 页。程序不会自动识别验证码、轮换代理或并发访问。遇到安全验证、403/429/503 或翻页异常会停止并保存已有结果。浏览器会话在本地 `.browser_profile/`，原始采集数据在 `output/`；两者均被 `.gitignore` 排除，**不要上传或分享浏览器会话**。请遵守[知网会员服务使用协议](https://wap.oversea.cnki.net/cn/member/agreement.html)，使用机构账号时也需遵守所在机构的访问规定。

知网页面结构可能变化。`--manual-search` 可用于网站检索控件改版后的临时操作；若解析字段发生变化，需要更新选择器。项目在 2026-09-25 通过了真实浏览器检索、排序及详情页采集验证，不能保证今后网站始终保持相同结构。

## 测试、许可与来源

```bash
.venv/bin/python -m unittest discover -s tests -v
```

本项目采用 [MIT 许可](LICENSE)。检索入口、结果字段与排序控件的设计参考了 MIT 许可的 [wuruiqi/cnki-mcp](https://github.com/wuruiqi/cnki-mcp)；本项目的限速、筛选、翻页、详情解析及导出流程为本仓库实现。上游署名和许可文本见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
