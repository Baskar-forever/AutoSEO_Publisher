"""
External Link Resolver
======================
Replaces the LLM's hallucinated external links with REAL, verified URLs
fetched directly from Serper (Google Search API).

No LLM involved — pure deterministic search + HTTP verification.

How it works:
  1. Parse the article HTML and find all external <a> links
  2. For each link, extract the anchor text (what the link says)
  3. Search Serper for that anchor text → get real Google results
  4. HTTP-verify each candidate → pick the first live one
  5. Replace the fake href with the verified real URL

This runs AFTER the LLM writes the article but BEFORE link_audit,
so link_audit sees only real URLs and keeps them all.
"""

import os
import re
import time
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup, NavigableString
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
TIMEOUT        = 10
SLEEP_BETWEEN  = 0.3   # seconds between Serper calls (rate limit safety)

# Domains we trust as authoritative external sources
AUTHORITY_DOMAINS = {
    "reuters.com", "cnbc.com", "techcrunch.com", "theverge.com",
    "wired.com", "arstechnica.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "bloomberg.com", "forbes.com", "wsj.com",
    "venturebeat.com", "zdnet.com", "engadget.com", "thenextweb.com",
    "cnet.com", "medium.com", "towardsdatascience.com",
    "developer.mozilla.org", "github.com", "wikipedia.org",
    "openai.com", "news.ycombinator.com", "mashable.com",
    "aws.amazon.com", "cloud.google.com", "azure.microsoft.com",
    "docs.python.org", "pytorch.org", "tensorflow.org",
    "ft.com", "apnews.com", "washingtonpost.com", "economist.com",
    "mit.edu", "stanford.edu", "nature.com", "science.org",
}

AUTHORITY_TLDS = (".gov", ".edu", ".ac.uk", ".ac.in")


def _is_authoritative(url: str) -> bool:
    host = urlparse(url).netloc.lower().lstrip("www.")
    if any(host == d or host.endswith("." + d) for d in AUTHORITY_DOMAINS):
        return True
    if any(host.endswith(tld) for tld in AUTHORITY_TLDS):
        return True
    return False


def _is_fake_url(url: str) -> bool:
    """Detect hallucinated / example URLs or explicit pipeline placeholders."""
    # Explicit pipeline placeholder set by the writer agent
    if url.strip() in ("SERPER_RESOLVE", "SERPER_RESOLVE/", "#SERPER_RESOLVE"):
        return True
    patterns = [
        r"example\.com",
        r"yourdomain\.com",
        r"placeholder",
        r"\*{2,}",
        r"yoursite\.",
        r"localhost",
        r"127\.0\.0\.1",
        r"SERPER_RESOLVE",
    ]
    for p in patterns:
        if re.search(p, url, re.IGNORECASE):
            return True
    return False


def _verify_url(url: str) -> bool:
    """Returns True if URL is reachable (HTTP 200)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AutoSEOBot/1.0)"}
        r = requests.head(url, allow_redirects=True, timeout=TIMEOUT, headers=headers)
        if r.status_code == 200:
            return True
        if r.status_code in (405, 403):
            r2 = requests.get(url, allow_redirects=True, timeout=TIMEOUT,
                              headers=headers, stream=True)
            return r2.status_code == 200
        return False
    except Exception:
        return False


def _search_serper(query: str, num: int = 5) -> list[dict]:
    """
    Search Serper for `query`, return list of {title, url} dicts.
    Returns [] on any error so the pipeline never hard-fails.
    """
    if not SERPER_API_KEY:
        print("⚠️  external_link_resolver: SERPER_API_KEY not set")
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=15,
        )
        r.raise_for_status()
        results = []
        for item in r.json().get("organic", []):
            link = item.get("link", "")
            title = item.get("title", "")
            if link and title:
                results.append({"title": title, "url": link})
        return results
    except Exception as e:
        print(f"⚠️  external_link_resolver: Serper error — {e}")
        return []


def _find_real_url(anchor_text: str, article_topic: str) -> str | None:
    """
    Given the anchor text of a link and the article topic,
    search Serper to find a real authoritative URL.
    Returns the first verified URL, or None.
    """
    # Try two queries: specific anchor text first, then anchor+topic
    queries = [
        f"{anchor_text} site:reuters.com OR site:cnbc.com OR site:techcrunch.com OR site:theverge.com OR site:wired.com OR site:bbc.com OR site:bloomberg.com",
        f"{anchor_text} {article_topic}",
    ]

    for query in queries:
        candidates = _search_serper(query, num=5)
        time.sleep(SLEEP_BETWEEN)

        for candidate in candidates:
            url = candidate["url"]
            if not _is_authoritative(url):
                continue
            if _verify_url(url):
                print(f"  ✅ Resolved: '{anchor_text}' → {url}")
                return url

    print(f"  ⚠️  Could not find real URL for anchor: '{anchor_text}'")
    return None


def resolve_external_links(html: str, article_topic: str = "") -> str:
    """
    Main entry point.
    Scans html for external links with fake/hallucinated hrefs.
    Replaces each with a real Serper-verified URL.
    Removes the link entirely if no real URL can be found.

    Returns updated HTML.
    """
    soup = BeautifulSoup(html, "html.parser")
    wp_domain = urlparse(os.getenv("WP_URL", "")).netloc

    fake_count    = 0
    resolved      = 0
    removed       = 0

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        parsed = urlparse(href)

        # Skip internal links, fragments, mailto, tel
        if not href.startswith("http"):
            continue
        if wp_domain and wp_domain in parsed.netloc:
            continue

        # Only process fake/hallucinated URLs
        if not _is_fake_url(href):
            continue

        fake_count += 1
        anchor_text = tag.get_text(strip=True)

        if not anchor_text:
            tag.decompose()
            removed += 1
            continue

        print(f"\n🔍 Resolving fake external link: '{anchor_text}' (was: {href})")
        real_url = _find_real_url(anchor_text, article_topic)

        if real_url:
            tag["href"]   = real_url
            tag["target"] = "_blank"
            tag["rel"]    = "noopener noreferrer"
            resolved += 1
        else:
            # No real URL found — unwrap to plain text, keep reading flow
            tag.replace_with(NavigableString(anchor_text))
            removed += 1

    print(f"\n🔗 External link resolution: {fake_count} fake links found | "
          f"{resolved} resolved | {removed} removed")

    return str(soup)