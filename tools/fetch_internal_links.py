import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from crewai.tools import tool

import os
base_url = os.getenv("WP_URL", "https://yourdomain.com/")

TIMEOUT = 10
MAX_VERIFY_WORKERS = 8  # parallel HEAD checks

TOOL_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "dummy_arg": {"type": "string", "description": "Dummy argument to satisfy strict API schema requirements.", "default": "dummy"}
    },
    "required": []
}


def _verify_url_alive(url: str) -> bool:
    """
    Returns True only if the URL responds with HTTP 200.
    Tries HEAD first (fast), falls back to GET if HEAD fails
    (some servers reject HEAD with 405 or 403).
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AutoSEOBot/1.0)"}
    try:
        r = requests.head(url, allow_redirects=True, timeout=TIMEOUT, headers=headers)
        if r.status_code == 200:
            return True
        if r.status_code in (405, 403):
            # Server rejected HEAD — retry with GET
            r2 = requests.get(url, allow_redirects=True, timeout=TIMEOUT,
                              headers=headers, stream=True)
            return r2.status_code == 200
        return False
    except Exception:
        return False


@tool("Fetch Internal Links Tool")
def get_all_internal_links(dummy_arg: str = "dummy"):
    """
    Fetches all LIVE internal links from the given base URL.
    Every collected URL is verified with an HTTP check — broken,
    deleted, or redirected-to-404 pages are excluded so that AI
    agents never receive a stale or missing URL.
    """

    visited = set()
    to_visit = {base_url}
    candidate_links = set()   # collected from crawl (may include stale URLs)

    domain = urlparse(base_url).netloc

    # ── Phase 1: Crawl and collect candidate internal URLs ────────────────────
    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, timeout=TIMEOUT)
            if resp.status_code != 200:
                continue                # skip pages that don't load
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            href = urljoin(base_url, href)
            parsed = urlparse(href)

            # Only same-domain links
            if parsed.netloc != domain:
                continue

            # Skip mailto / tel / javascript / fragment-only
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue

            # Normalise: strip query strings and fragments
            clean = parsed.scheme + "://" + parsed.netloc + parsed.path
            clean = clean.rstrip("/") or clean

            if clean not in candidate_links:
                candidate_links.add(clean)
                to_visit.add(clean)

        time.sleep(0.5)  # be polite

    # ── Phase 2: Verify every candidate is actually alive (parallel HEAD) ─────
    print(f"🔍 Verifying {len(candidate_links)} candidate internal links...")

    live_links = set()
    with ThreadPoolExecutor(max_workers=MAX_VERIFY_WORKERS) as pool:
        future_map = {
            pool.submit(_verify_url_alive, url): url
            for url in candidate_links
        }
        for future in as_completed(future_map):
            url = future_map[future]
            try:
                if future.result():
                    live_links.add(url)
                else:
                    print(f"⚠️  Excluded dead internal URL: {url}")
            except Exception as exc:
                print(f"⚠️  Verify error for {url}: {exc}")

    print(f"✅ {len(live_links)} live internal links ready for use "
          f"({len(candidate_links) - len(live_links)} dead URLs excluded)")

    return live_links


# Attach JSON schema to the tool function object so the tool registry can see inputs
try:
    get_all_internal_links.args = TOOL_ARGS_SCHEMA
except Exception:
    pass