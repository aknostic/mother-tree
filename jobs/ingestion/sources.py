"""Content source readers.

Three source types:
- Foundation (git repos, sitemaps) → extract change, worldview, personas, competitors
- Narrative (sitemaps) → extract stories, evidence, reframes
- Conversation → not ingested, entered by humans
"""

import hashlib
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# --- Git repo reader ---

def read_repo_markdown(repo_path: str) -> list[dict]:
    """Read all .md files from a git repo. No hardcoded file list."""
    repo = Path(repo_path)
    results = []
    for filepath in sorted(repo.rglob("*.md")):
        # Skip hidden dirs, node_modules, etc.
        parts = filepath.relative_to(repo).parts
        if any(p.startswith(".") or p == "node_modules" for p in parts):
            continue
        relpath = str(filepath.relative_to(repo))
        content = filepath.read_text(encoding="utf-8")
        # Skip very short files (READMEs with just a title, etc.)
        if len(content) < 100:
            continue
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        results.append({
            "path": relpath,
            "content": content,
            "content_hash": content_hash,
            "source": f"repo:{relpath}",
        })
    return results


# --- Sitemap reader ---

def fetch_sitemap_urls(sitemap_url: str) -> list[dict]:
    """Fetch sitemap.xml and return list of {url, lastmod}."""
    resp = httpx.get(sitemap_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml-xml")
    urls = []
    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc")
        lastmod = url_tag.find("lastmod")
        if loc:
            urls.append({
                "url": loc.text.strip(),
                "lastmod": lastmod.text.strip() if lastmod else None,
            })
    return urls


def fetch_page_content(url: str) -> str | None:
    """Fetch a web page and extract the article text."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"    Failed to fetch {url}: {e}")
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_="content")
        or soup.find("div", class_="post")
        or soup.body
    )
    if not article:
        return None
    for tag in article.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = article.get_text(separator="\n", strip=True)
    if len(text) < 200:
        return None
    if len(text) > 12000:
        text = text[:12000]
    return text


def filter_urls(urls: list[dict], path_filters: list[str] | None) -> list[dict]:
    """Filter sitemap URLs by path prefix."""
    if not path_filters:
        return urls
    return [u for u in urls if any(f in u["url"] for f in path_filters)]
