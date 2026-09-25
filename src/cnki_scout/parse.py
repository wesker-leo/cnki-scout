"""Parse CNKI's rendered pages. Selectors were adapted from wuruiqi/cnki-mcp (MIT)."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\n\r;；")


def first_text(node: Tag | BeautifulSoup, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        hit = node.select_one(selector)
        if hit:
            value = clean(hit.get_text(" ", strip=True))
            if value:
                return value
    return ""


def count(text: str) -> int | None:
    match = re.search(r"\d[\d,]*", text)
    return int(match.group().replace(",", "")) if match else None


def safe_cnki_url(href: str, base: str) -> str:
    url = urljoin(base, href)
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not (parts.hostname == "cnki.net" or (parts.hostname or "").endswith(".cnki.net")):
        return ""
    return urlunparse(parts._replace(scheme="https"))


def parse_results(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[Tag] = []
    for selector in (".result-table-list tbody tr", "#gridTable table tr", "#gridTable tbody tr"):
        found = soup.select(selector)
        if found:
            rows = found
            break
    results = []
    for row in rows:
        title_link = row.select_one("td.name a[href], a.fz14[href], .name a[href]")
        if not title_link:
            continue
        title = clean(title_link.get_text(" ", strip=True))
        url = safe_cnki_url(title_link.get("href", ""), base_url)
        if not title or not url:
            continue
        date = first_text(row, ("td.date", ".date"))
        database = first_text(row, ("td.data", "td.database", ".database"))
        results.append({
            "title": title,
            "url": url,
            "authors": first_text(row, ("td.author", ".author")),
            "source": first_text(row, ("td.source", ".source")),
            "publication_date": date,
            "database": database,
            "citations": count(first_text(row, ("td.quote", ".quote", "td.cited", ".cited"))),
            "downloads": count(first_text(row, ("td.download", ".download"))),
        })
    return results


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def _meta_all(soup: BeautifulSoup, name: str) -> list[str]:
    return [clean(tag.get("content")) for tag in soup.find_all("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)}) if clean(tag.get("content"))]


def _labeled(soup: BeautifulSoup, label: str) -> str:
    # Only inspect short metadata blocks; searching the whole page can mix in references.
    for tag in soup.select("li, p, dt"):
        text = clean(tag.get_text(" ", strip=True))
        if len(text) > 250:
            continue
        if tag.name == "dt" and text.strip("：:") == label:
            sibling = tag.find_next_sibling("dd")
            if sibling:
                return clean(sibling.get_text(" ", strip=True))
        match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(.+)$", text, re.I)
        if match:
            return clean(match.group(1))
    return ""


def _split_keywords(value: str) -> list[str]:
    return [part for part in (clean(x) for x in re.split(r"[;；]", value)) if part]


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    abstract = _meta(soup, "citation_abstract", "DC.Description") or first_text(
        soup, ("#ChDivSummary", "#ChDivSummaryMore", ".abstract-text", ".abstract")
    )
    abstract = re.sub(r"\s*(更多|还原)\s*$", "", abstract)
    keyword_nodes = soup.select(".keywords a, #catalog_KEYWORD a")
    if keyword_nodes:
        keywords = [clean(node.get_text(" ", strip=True)) for node in keyword_nodes]
        keywords = [word for word in keywords if word]
    else:
        keywords = _split_keywords(_meta(soup, "citation_keywords", "keywords") or _labeled(soup, "关键词") or first_text(soup, (".keywords",)))
    institution_nodes = soup.select(".orgn a, .author-unit a") or soup.select(".orgn, .author-unit")
    institutions = [clean(tag.get_text(" ", strip=True)) for tag in institution_nodes]
    if not institutions:
        author_blocks = soup.select(".wx-tit h3.author")
        if len(author_blocks) > 1:
            institutions = [re.sub(r"^\d+[.、]\s*", "", clean(tag.get_text(" ", strip=True))) for tag in author_blocks[1].select("a")]
    if not institutions:
        institutions = _split_keywords(_labeled(soup, "作者单位"))
    institutions = list(dict.fromkeys(item for item in institutions if item))
    doi = _meta(soup, "citation_doi", "DC.Identifier") or _labeled(soup, "DOI")
    match = re.search(r"10\.\d{4,9}/[^\s;；]+", doi, re.I)
    doi = match.group().rstrip(".,，。") if match else ""
    return {
        "abstract": clean(abstract),
        "keywords": list(dict.fromkeys(keywords)),
        "institutions": institutions,
        "doi": doi,
        "collection": _labeled(soup, "专辑"),
        "topic": _labeled(soup, "专题"),
        "discipline": _labeled(soup, "学科专业"),
        "database_detail": _labeled(soup, "数据库"),
        "detail_title": _meta(soup, "citation_title") or first_text(soup, (".brief h1", "h1")),
        "detail_authors": "; ".join(_meta_all(soup, "citation_author")),
        "detail_source": _meta(soup, "citation_journal_title"),
        "detail_publication_date": _meta(soup, "citation_date", "citation_publication_date"),
    }
