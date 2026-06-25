"""
Topic Guard — Duplicate & Staleness Prevention
===============================================
Two jobs:
  1. fetch_published_topics()  — pulls all published post titles + slugs
     from the WP REST API so the Trend Researcher knows what already exists.

  2. is_duplicate_topic(candidate, published)  — fuzzy-matches a proposed
     topic against the published list; returns True if too similar.

Used in:
  - main.py  (before article generation starts)
  - trend_keyword_tool.py  (injects history into the search query)
"""

import os
import re
import requests
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

WP_URL        = os.getenv("WP_URL", "").rstrip("/")
WP_USER       = os.getenv("WP_USER", "")
WP_APP_PASS   = os.getenv("WP_APP_PASSWORD", "")
TIMEOUT       = 10
SIMILARITY_THRESHOLD = 0.55   # 0–1; lower = stricter duplicate detection


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Lowercase, strip numbers/years/punctuation for fair comparison."""
    text = text.lower()
    text = re.sub(r"\b(20\d{2}|top|best|guide|ultimate|amazing|proven|"
                  r"complete|ways|secrets|tips|how to|what is|why)\b", " ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_published_topics() -> list[dict]:
    """
    Returns list of dicts: {title, slug, url, date}
    Fetches from WP REST API — no auth needed for public posts.
    Falls back to [] on any error so the pipeline never hard-fails.
    """
    if not WP_URL:
        return []

    results = []
    for endpoint in ["/wp-json/wp/v2/posts", "/wp-json/wp/v2/pages"]:
        page = 1
        while True:
            try:
                r = requests.get(
                    f"{WP_URL}{endpoint}",
                    params={
                        "per_page": 100,
                        "page": page,
                        "_fields": "title,slug,link,date",
                        "status": "publish",
                    },
                    timeout=TIMEOUT,
                )
                if r.status_code != 200:
                    break
                items = r.json()
                if not items:
                    break
                for item in items:
                    results.append({
                        "title": item.get("title", {}).get("rendered", ""),
                        "slug":  item.get("slug", ""),
                        "url":   item.get("link", ""),
                        "date":  item.get("date", "")[:10],   # YYYY-MM-DD
                    })
                page += 1
            except Exception as exc:
                print(f"⚠️  topic_guard: WP REST fetch failed — {exc}")
                break

    print(f"📚 topic_guard: loaded {len(results)} published posts from WordPress")
    return results


def is_duplicate_topic(candidate_title: str, published: list[dict]) -> bool:
    """
    Returns True if candidate_title is too similar to any published post.
    Also catches year-staleness: if the candidate contains a year < current year.
    """
    from datetime import datetime
    current_year = datetime.now().year

    # Check for stale year in candidate title
    years_in_title = re.findall(r"\b(20\d{2})\b", candidate_title)
    for y in years_in_title:
        if int(y) < current_year:
            print(f"🕰️  topic_guard: stale year {y} found in candidate — rejecting")
            return True

    # Fuzzy match against all published titles and slugs
    for post in published:
        title_sim  = _similarity(candidate_title, post["title"])
        slug_sim   = _similarity(candidate_title, post["slug"].replace("-", " "))
        if max(title_sim, slug_sim) >= SIMILARITY_THRESHOLD:
            print(f"🔁 topic_guard: duplicate detected\n"
                  f"   Candidate : {candidate_title}\n"
                  f"   Matches   : {post['title']} ({post['url']})\n"
                  f"   Similarity: {max(title_sim, slug_sim):.2f}")
            return True

    return False


def build_exclusion_brief(published: list[dict], max_items: int = 30) -> str:
    """
    Returns a plain-text summary of recent posts to inject into the
    Trend Researcher prompt so the LLM avoids similar topics.
    """
    if not published:
        return "No previously published posts found."

    # Sort by date descending, take most recent N
    sorted_posts = sorted(published, key=lambda p: p["date"], reverse=True)
    lines = ["Recently published posts (DO NOT repeat these topics or close variants):"]
    for p in sorted_posts[:max_items]:
        lines.append(f"  - [{p['date']}] {p['title']}  →  {p['url']}")
    return "\n".join(lines)