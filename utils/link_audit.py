"""
 Production-grade Link Auditor for AutoSEO Publisher

"""

import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
from typing import Optional

import requests
from bs4 import BeautifulSoup, NavigableString

# ── Logging ────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ── Constants ──────────────────────────────────────────────────────────────────
TIMEOUT = 10          # seconds per HTTP call
MAX_WORKERS = 6       # parallel link checks (safe for most CI runners)
RETRY_GET_ON_HEAD_FAIL = True  # fall back to GET if HEAD returns error

AUTHORITY_DOMAINS = {
    # Tech / News
    "medium.com", "reddit.com", "developer.mozilla.org", "stackoverflow.com",
    "github.com", "wikipedia.org", "google.com", "openai.com",
    "news.ycombinator.com", "techcrunch.com", "theverge.com", "wired.com",
    "arstechnica.com", "reuters.com", "cnbc.com", "bbc.com", "bbc.co.uk",
    "nytimes.com", "bloomberg.com", "forbes.com", "wsj.com",
    "venturebeat.com", "zdnet.com", "engadget.com", "thenextweb.com",
    "mashable.com", "cnet.com", "towardsdatascience.com",
    "aws.amazon.com", "cloud.google.com", "azure.microsoft.com",
    "docs.python.org", "pytorch.org", "tensorflow.org",
    # Trustworthy TLD patterns checked separately below
}

AUTHORITY_TLDS = (".gov", ".edu", ".ac.uk", ".ac.in")

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AutoSEOBot/1.0; "
        "+https://github.com/Baskar-forever/AutoSEO_Publisher)"
    )
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_authoritative(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if any(host == d or host.endswith("." + d) for d in AUTHORITY_DOMAINS):
        return True
    if any(host.endswith(tld) for tld in AUTHORITY_TLDS):
        return True
    return False


def _check_url(url: str) -> tuple[Optional[int], Optional[str]]:
    """
    Returns (status_code, final_url) after following redirects.
    Tries HEAD first; falls back to GET (stream=True) if HEAD fails or
    returns a suspicious status.
    """
    try:
        r = requests.head(
            url, allow_redirects=True,
            timeout=TIMEOUT, headers=_REQUEST_HEADERS
        )
        if r.status_code < 400:
            return r.status_code, r.url
        if not RETRY_GET_ON_HEAD_FAIL:
            return r.status_code, r.url
        # Some servers (Cloudflare, Medium) reject HEAD — retry with GET
        r2 = requests.get(
            url, allow_redirects=True, stream=True,
            timeout=TIMEOUT, headers=_REQUEST_HEADERS
        )
        return r2.status_code, r2.url
    except requests.exceptions.SSLError:
        logger.warning("SSL error → %s", url)
        return None, None
    except requests.exceptions.ConnectionError:
        logger.warning("Connection error → %s", url)
        return None, None
    except requests.exceptions.Timeout:
        logger.warning("Timeout → %s", url)
        return None, None
    except Exception as exc:
        logger.warning("Unexpected error checking %s: %s", url, exc)
        return None, None


def _fetch_wp_slugs(base_url: str) -> set[str]:
    """
    Queries the WP REST API for published post & page slugs.
    Returns a set of full URLs (normalised, no trailing slash).
    Falls back to empty set so the pipeline never hard-fails.
    """
    slugs: set[str] = set()
    domain = base_url.rstrip("/")
    for endpoint in ["/wp-json/wp/v2/posts", "/wp-json/wp/v2/pages"]:
        page = 1
        while True:
            try:
                r = requests.get(
                    f"{domain}{endpoint}",
                    params={"per_page": 100, "page": page, "_fields": "link"},
                    timeout=TIMEOUT,
                    headers=_REQUEST_HEADERS,
                )
                if r.status_code != 200:
                    break
                items = r.json()
                if not items:
                    break
                for item in items:
                    link = item.get("link", "").rstrip("/")
                    if link:
                        slugs.add(link)
                page += 1
            except Exception as exc:
                logger.warning("WP REST API fetch failed: %s", exc)
                break
    logger.info("✅ Fetched %d known WP URLs from REST API", len(slugs))
    return slugs


def _is_known_internal(url: str, known_slugs: set[str]) -> bool:
    """True if url (normalised) is in the known slug set."""
    normalised = url.rstrip("/")
    return normalised in known_slugs


# ── Core audit function ────────────────────────────────────────────────────────

def audit_and_fix_links(
    html: str,
    base_url: Optional[str] = None,
    *,
    prefetch_wp_slugs: bool = True,
) -> tuple[str, dict]:
    """
    Audit every <a href> in `html`.

    Returns
    -------
    (fixed_html: str, report: dict)
        report keys: total, kept, fixed_redirect, stripped_broken,
                     stripped_unauthoritative, stripped_internal_404,
                     skipped_fragment
    """
    if base_url is None:
        base_url = os.getenv("WP_URL", "https://yourdomain.com/")

    site_domain = urlparse(base_url).netloc
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)

    # ── 1. Pre-fetch known WP slugs (once, not per-link) ──────────────────────
    known_slugs: set[str] = set()
    if prefetch_wp_slugs and site_domain not in ("yourdomain.com", "example.com"):
        known_slugs = _fetch_wp_slugs(base_url)

    # ── 2. Build work list: resolve every href to an absolute URL ─────────────
    work: list[tuple] = []  # (tag, full_url, is_internal, is_fragment)
    for tag in anchors:
        href = tag["href"].strip()

        # Skip mailto / tel / javascript
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue

        # Skip LLM-hallucinated placeholder hrefs — remove entire parent <li> if present
        if _is_placeholder_href(href):
            parent = tag.parent
            if parent and parent.name == "li":
                parent.decompose()
            else:
                tag.decompose()
            logger.info("🗑️  Removed placeholder link: %s", href)
            continue

        # Fragment-only links → always keep (TOC anchors, etc.)
        if href.startswith("#"):
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/") or full_url
        is_internal = site_domain in parsed.netloc

        work.append((tag, clean_url, is_internal))

    # ── 3. Parallel HTTP checks ────────────────────────────────────────────────
    url_results: dict[str, tuple[Optional[int], Optional[str]]] = {}

    # Deduplicate URLs to avoid redundant checks
    unique_urls = {url for _, url, _ in work}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(_check_url, url): url for url in unique_urls}
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                url_results[url] = future.result()
            except Exception as exc:
                logger.warning("Future error for %s: %s", url, exc)
                url_results[url] = (None, None)

    # ── 4. Apply fixes to the DOM ──────────────────────────────────────────────
    stats = {
        "total": len(work),
        "kept": 0,
        "fixed_redirect": 0,
        "stripped_broken": 0,
        "stripped_unauthoritative": 0,
        "stripped_internal_404": 0,
        "skipped_fragment": len(anchors) - len(work),
    }

    for tag, clean_url, is_internal in work:
        status, final_url = url_results.get(clean_url, (None, None))

        # ── Broken / unreachable ──────────────────────────────────────────────
        if status is None or status >= 400:
            logger.info("✂️  Stripping broken link (%s) → %s", status, clean_url)
            _unwrap_preserving_text(tag)
            if is_internal:
                stats["stripped_internal_404"] += 1
            else:
                stats["stripped_broken"] += 1
            continue

        # ── Redirect: update href to canonical URL ────────────────────────────
        if final_url and final_url.rstrip("/") != clean_url:
            logger.info("🔁 Redirect fixed: %s → %s", clean_url, final_url)
            clean_url = final_url.rstrip("/")
            stats["fixed_redirect"] += 1

        # ── External link rules ───────────────────────────────────────────────
        if not is_internal:
            if not _is_authoritative(clean_url):
                logger.info("✂️  Stripping non-authoritative link → %s", clean_url)
                _unwrap_preserving_text(tag)
                stats["stripped_unauthoritative"] += 1
                continue

            tag["href"] = clean_url
            tag["rel"] = "noopener noreferrer"   # BUG-7 fix: add noreferrer
            tag["target"] = "_blank"
            stats["kept"] += 1
            continue

        # ── Internal link rules ───────────────────────────────────────────────
        # Validate against known slugs — WP REST API is the ground truth.
        # WordPress often returns 200 for guessed /blog/slug paths (redirects
        # to blog index) so HTTP-200 alone is NOT sufficient for internal links.
        if known_slugs:
            if not _is_known_internal(clean_url, known_slugs):
                logger.info("✂️  Stripping internal URL not in WP REST → %s", clean_url)
                _unwrap_preserving_text(tag)
                stats["stripped_internal_404"] += 1
                continue
        else:
            # No WP REST data — fall back to strict: only allow URLs the
            # crawler actually visited and confirmed (no /blog/ guesses).
            import re as _re2
            path = urlparse(clean_url).path
            if _re2.search(r"^/blog/", path):
                logger.info("✂️  Stripping unverified /blog/ path (no WP REST data) → %s", clean_url)
                _unwrap_preserving_text(tag)
                stats["stripped_internal_404"] += 1
                continue

        tag["href"] = clean_url
        # Remove any accidental target/rel on internal links
        for attr in ("target", "rel"):
            if tag.get(attr) is not None:
                del tag[attr]
        stats["kept"] += 1

    logger.info(
        "🔗 Link audit complete | total=%d kept=%d "
        "fixed_redirect=%d stripped_broken=%d "
        "stripped_unauthoritative=%d stripped_internal_404=%d",
        stats["total"], stats["kept"],
        stats["fixed_redirect"], stats["stripped_broken"],
        stats["stripped_unauthoritative"], stats["stripped_internal_404"],
    )
    return str(soup), stats



import re as _re

def _is_placeholder_href(href: str) -> bool:
    """Detect fake/hallucinated hrefs the LLM writes when it has no real URLs."""
    if not href or href.strip() in ("#", "", "javascript:void(0)"):
        return True
    patterns = [
        r"^\*{2,}",                  # starts with ***
        r"^https?://example",          # example.com
        r"internal[\s_-]?link",       # "internal-link" as href
        r"^/blog/\.\.\.",           # /blog/...
        r"#your-",                     # #your-section
        r"placeholder",                # anything with placeholder
        r"^your-",                     # your-slug
        r"/blog/[a-z0-9-]+-(?:trends|growth|insights|strategies|guide|tips|news|review|analysis|updates)$",  # LLM-guessed /blog/topic-keyword paths
    ]
    for pat in patterns:
        if _re.search(pat, href.strip(), _re.IGNORECASE):
            return True
    return False

def _unwrap_preserving_text(tag) -> None:
    """
    Replace <a href='...'>anchor text</a> with its plain text so prose
    remains grammatically intact after stripping the link. (BUG-2 fix)
    """
    text = tag.get_text()
    tag.replace_with(NavigableString(text))