"""
auto_categorizer.py  —  AutoSEO Publisher
==========================================
Automatically selects the most relevant WordPress category for a
generated article using a two-layer strategy:

  Layer 1 — Fast keyword matching (zero API cost, runs first)
  Layer 2 — LLM fallback (only fires when Layer 1 is ambiguous)

CATEGORY MAP (reader-friendly, 5 categories)
─────────────────────────────────────────────
  1. AI & Emerging Tech    → AI tools, LLMs, automation, robotics, Web3
  2. News & Trends         → Breaking news, market moves, industry updates
  3. Buying Guides & Reviews → Comparisons, product picks, recommendations
  4. How-To & Tutorials    → Step-by-step guides, setup, troubleshooting
  5. Career & Skills       → Jobs, learning paths, professional growth

HOW IT PLUGS IN
───────────────
  from utils.auto_categorizer import resolve_category_id

  category_id = resolve_category_id(
      title=seo_title,
      focus_keyword=focus_keyword,
      html_content=html_content,
      llm=llm,             # your CrewAI LLM instance
  )
  # Returns an int WP category ID, or None if lookup fails.
  # Pass it straight into post_to_wordpress() as categories=[category_id]
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Category definitions ───────────────────────────────────────────────────────

CATEGORIES: dict[str, dict] = {
    "AI & Emerging Tech": {
        "keywords": [
            "artificial intelligence", "machine learning", "deep learning",
            "large language model", "llm", "gpt", "chatgpt", "gemini",
            "claude", "generative ai", "neural network", "automation",
            "robotics", "blockchain", "web3", "cryptocurrency", "nft",
            "quantum computing", "ar ", "vr ", "augmented reality",
            "virtual reality", "autonomous", "ai tool", "ai model",
            "transformer", "diffusion model", "openai", "anthropic",
            "hugging face", "stable diffusion", "midjourney", "copilot",
        ],
    },
    "News & Trends": {
        "keywords": [
            "breaking", "announces", "announced", "launches", "launched",
            "releases", "released", "new study", "report", "survey",
            "funding", "acquisition", "ipo", "valuation", "startup",
            "raises", "partnership", "merger", "regulation", "ban",
            "policy", "government", "congress", "senate", "eu ai act",
            "trending", "2024", "2025", "2026", "this week", "today",
            "latest", "just released", "update", "patch",
        ],
    },
    "Buying Guides & Reviews": {
        "keywords": [
            "best ", "top ", "vs ", "versus", "comparison", "compared",
            "review", "buying guide", "should you buy", "worth it",
            "recommendation", "pick", "alternative", "cheaper",
            "budget", "premium", "price", "cost", "deal", "discount",
            "pros and cons", "ranked", "rating", "score out of",
            "tested", "hands on", "which is better",
        ],
        # Strong comparison signals that outweigh topic-level AI keywords
        "how_to_patterns": [
            r"\bvs\.?\b",
            r"\bversus\b",
            r"which\b.{0,25}\b(better|wins|best|winner)\b",
            r"\bcompare[sd]?\b",
            r"\bbest\s+\w+\s+(for|in)\b",
            r"\btop\s+\d+\b",
        ],
    },
    "How-To & Tutorials": {
        "how_to_patterns": [
            r"\bhow to\b", r"\bstep[- ]by[- ]step\b", r"\btutorial\b",
            r"\bguide\b", r"\bsetup\b", r"\binstall\b", r"\bconfigure\b",
            r"\bget started\b", r"\bbuild\b", r"\bcreate\b", r"\bfix\b",
            r"\btroubleshoot\b", r"\boptimize\b", r"\bimprove\b",
            r"\bmaster\b", r"\blearn\b", r"\bbeginners?\b",
        ],
        "keywords": [
            "how to", "step by step", "tutorial", "setup", "install",
            "configure", "troubleshoot", "walkthrough", "guide",
            "beginners", "get started", "cheat sheet", "tips",
            "tricks", "hack", "shortcut", "workflow", "automate",
            "script", "code", "api", "integration", "deploy",
        ],
    },
    "Career & Skills": {
        "keywords": [
            "career", "job", "jobs", "hiring", "layoff", "laid off",
            "resume", "interview", "salary", "skill", "skills",
            "upskill", "reskill", "learning", "course", "certification",
            "bootcamp", "degree", "university", "linkedin",
            "professional development", "freelance", "remote work",
            "productivity", "soft skills", "leadership", "management",
            "entrepreneur", "solopreneur", "side hustle", "income",
            "workforce", "future of work",
        ],
    },
}

# ── WordPress category cache ───────────────────────────────────────────────────

_wp_category_cache: dict[str, int] = {}   # {"AI & Emerging Tech": 12, ...}


def _fetch_wp_categories() -> dict[str, int]:
    """
    Pulls all categories from the WP REST API.
    Returns {name: id} mapping.  Falls back to {} on failure.
    """
    global _wp_category_cache
    if _wp_category_cache:
        return _wp_category_cache

    wp_url = os.getenv("WP_URL", "").rstrip("/")
    wp_user = os.getenv("WP_USER", "")
    wp_pass = os.getenv("WP_APP_PASSWORD", "")

    if not all([wp_url, wp_user, wp_pass]):
        logger.warning("WP credentials missing — category auto-assign disabled")
        return {}

    import base64
    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}

    try:
        r = requests.get(
            f"{wp_url}/wp-json/wp/v2/categories",
            params={"per_page": 100, "_fields": "id,name"},
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        for cat in r.json():
            _wp_category_cache[cat["name"]] = cat["id"]
        logger.info("✅ Fetched %d WP categories", len(_wp_category_cache))
    except Exception as exc:
        logger.warning("WP category fetch failed: %s", exc)

    return _wp_category_cache


# ── Layer 1: keyword scoring ───────────────────────────────────────────────────

def _extract_text_signals(title: str, focus_keyword: str, html_content: str) -> str:
    """
    Build a single lowercase string from:
      - article title  (weight ×4 — strongest signal for category)
      - focus keyword  (weight ×3)
      - first 500 words of body text  (weight ×1)
    Weighting is done by simple repetition so the scorer stays a plain counter.
    Title gets ×4 because the article type (vs/how-to/news) is almost always
    signalled in the title, and body AI-topic keywords should not override it.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    body_text = " ".join(soup.get_text().split()[:500])

    signals = (
        f"{title} " * 4
        + f"{focus_keyword} " * 3
        + body_text
    ).lower()
    return signals


def _keyword_score(text: str, category_name: str) -> int:
    """Count keyword + pattern hits for one category."""
    cat = CATEGORIES[category_name]
    score = 0

    for kw in cat.get("keywords", []):
        score += text.count(kw)

    for pattern in cat.get("how_to_patterns", []):
        score += len(re.findall(pattern, text))

    return score


def _pick_by_keywords(text: str) -> Optional[str]:
    """
    Returns the winning category name, or None if the result is ambiguous
    (top two categories are within 2 points of each other).
    """
    scores = {name: _keyword_score(text, name) for name in CATEGORIES}
    logger.info("Category keyword scores: %s", scores)

    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_name, best_score = sorted_cats[0]
    second_score = sorted_cats[1][1] if len(sorted_cats) > 1 else 0

    if best_score == 0:
        return None   # no signal at all → LLM fallback

    if (best_score - second_score) <= 2:
        return None   # too close to call → LLM fallback

    return best_name


# ── Layer 2: LLM fallback ─────────────────────────────────────────────────────

_CATEGORY_PROMPT = """\
You are an editorial classifier for a tech blog.

Given the article title, focus keyword, and a short excerpt, choose the SINGLE most
appropriate category from this list:

  1. AI & Emerging Tech      — AI tools, LLMs, automation, robotics, Web3
  2. News & Trends           — Breaking news, funding, product launches, industry updates
  3. Buying Guides & Reviews — Comparisons, product picks, "best X" lists, reviews
  4. How-To & Tutorials      — Step-by-step guides, setup, troubleshooting, tutorials
  5. Career & Skills         — Jobs, learning paths, upskilling, professional growth

Return ONLY the category name exactly as written above. No explanation, no punctuation.
"""


def _pick_by_llm(
    title: str,
    focus_keyword: str,
    html_content: str,
    llm,
) -> Optional[str]:
    """
    Asks the CrewAI LLM to classify the article.
    Returns a matching category name or None on failure.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    excerpt = " ".join(soup.get_text().split()[:150])

    user_msg = (
        f"Title: {title}\n"
        f"Focus keyword: {focus_keyword}\n"
        f"Excerpt: {excerpt}"
    )

    messages = [
        {"role": "system", "content": _CATEGORY_PROMPT},
        {"role": "user",   "content": user_msg},
    ]

    try:
        raw = llm.call(messages).strip().rstrip(".")
        logger.info("LLM category response: %r", raw)

        # Fuzzy match against known names (handle slight wording drift)
        for name in CATEGORIES:
            if name.lower() in raw.lower() or raw.lower() in name.lower():
                return name

        logger.warning("LLM returned unrecognised category: %r", raw)
    except Exception as exc:
        logger.warning("LLM category call failed: %s", exc)

    return None


# ── Public API ─────────────────────────────────────────────────────────────────

DEFAULT_CATEGORY = "AI & Emerging Tech"


def classify_article(
    title: str,
    focus_keyword: str,
    html_content: str,
    llm=None,
) -> str:
    """
    Returns the best matching category NAME (str) for the article.

    Strategy:
      1. Keyword scoring  — fast, no API call
      2. LLM fallback     — only when keywords are ambiguous or silent
      3. Hard default     — "AI & Emerging Tech" if both layers fail
    """
    text = _extract_text_signals(title, focus_keyword, html_content)

    # Layer 1
    winner = _pick_by_keywords(text)
    if winner:
        logger.info("✅ Category decided by keywords: %s", winner)
        return winner

    # Layer 2
    if llm is not None:
        winner = _pick_by_llm(title, focus_keyword, html_content, llm)
        if winner:
            logger.info("✅ Category decided by LLM: %s", winner)
            return winner

    logger.info("⚠️  Falling back to default category: %s", DEFAULT_CATEGORY)
    return DEFAULT_CATEGORY


def resolve_category_id(
    title: str,
    focus_keyword: str,
    html_content: str,
    llm=None,
) -> Optional[int]:
    """
    Full pipeline entry point.

    1. Classify article → category name
    2. Look up WP category ID from REST API
    3. Return the int ID, or None if WP lookup fails

    Usage in wordpress_uploader.py:
        category_id = resolve_category_id(title, focus_keyword, html_content, llm)
        # then add to your post payload:
        if category_id:
            payload["categories"] = [category_id]
    """
    category_name = classify_article(title, focus_keyword, html_content, llm)
    print(f"🏷️  Auto-selected category: {category_name}")

    wp_cats = _fetch_wp_categories()

    if not wp_cats:
        # WP API unavailable — return name so caller can log it
        logger.warning("WP category map unavailable; returning name only")
        return None

    cat_id = wp_cats.get(category_name)
    if cat_id is None:
        # Try case-insensitive fallback
        for name, cid in wp_cats.items():
            if name.lower() == category_name.lower():
                cat_id = cid
                break

    if cat_id:
        print(f"   → WordPress category ID: {cat_id}")
    else:
        print(f"   ⚠️  '{category_name}' not found in WordPress. "
              f"Available: {list(wp_cats.keys())}")

    return cat_id