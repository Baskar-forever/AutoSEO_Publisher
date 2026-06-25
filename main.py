# main.py  —  Full SEO Article Generation & WordPress Publishing Pipeline
"""
Integrates: Article generation, image optimization, SEO validation,
FAQ injection, Table of Contents, duplicate prevention, and noindex control.
"""
import os
import re
import argparse
from datetime import datetime
from dotenv import load_dotenv

from article_generater import ArticleGenerator
from utils.link_audit import audit_and_fix_links
from utils.faq_injector import inject_faq_section
from utils.image_optimizer import optimize_image
from utils.toc_generator import inject_toc
from utils.topic_guard import (
    fetch_published_topics,
    is_duplicate_topic,
    build_exclusion_brief,
)
from tools.trend_keyword_tool import set_exclusion_brief
from wordpress_uploader import upload_image_to_wordpress, process_and_publish

load_dotenv()

MIN_SEO_SCORE    = 80
MAX_RETRY_TOPICS = 3   # how many times to retry if a duplicate topic is picked


def extract_title_from_html(html: str) -> str:
    """Pull the <h1> or <title> from the generated HTML for duplicate checking."""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def run_pipeline(noindex: bool = True, force_publish: bool = False):
    print("=" * 60)
    print("🚀 Starting Full SEO Article Generation Pipeline")
    print(f"📅 Current date: {datetime.now().strftime('%B %d, %Y')}")
    print("=" * 60)

    # ── Step 0: Load published topics for duplicate prevention ────────────────
    print("\n🔍 Step 0: Loading published post history from WordPress...")
    published_topics = fetch_published_topics()
    exclusion_brief  = build_exclusion_brief(published_topics)
    print(exclusion_brief[:500] + "..." if len(exclusion_brief) > 500 else exclusion_brief)

    # Inject the exclusion list into the trend tool BEFORE the crew starts
    set_exclusion_brief(exclusion_brief)

    # ── Step 1: Generate Article (with duplicate retry loop) ──────────────────
    html_output        = None
    local_image_path   = None
    attempt            = 0

    while attempt < MAX_RETRY_TOPICS:
        attempt += 1
        print(f"\n📝 Step 1 (attempt {attempt}/{MAX_RETRY_TOPICS}): Generating article content...")

        generator    = ArticleGenerator()
        html_output, local_image_path = generator.generate_article()

        if not html_output:
            print("❌ Article generation failed. Exiting.")
            return None

        # Extract the generated title and check for duplicates
        generated_title = extract_title_from_html(html_output)
        print(f"\n📌 Generated title: {generated_title}")

        if is_duplicate_topic(generated_title, published_topics):
            print(f"\n⚠️  Duplicate detected on attempt {attempt}. Regenerating with a different topic...")
            if attempt >= MAX_RETRY_TOPICS:
                print("❌ Max retries reached — could not find a unique topic. Exiting.")
                return None
            # Tell the trend tool to be even more specific on retry
            set_exclusion_brief(
                exclusion_brief + f"\n\n⛔ ALSO AVOID: '{generated_title}' — just tried this, pick something completely different."
            )
            continue

        print(f"✅ Unique topic confirmed: {generated_title}")
        break

    # ── Step 2: Inject Table of Contents ──────────────────────────────────────
    print("\n📑 Step 2: Generating Table of Contents...")
    html_output = inject_toc(html_output)

    # ── Step 3: Audit and Fix Links ───────────────────────────────────────────
    print("\n🔗 Step 3: Auditing and fixing links...")
    html_output, link_report = audit_and_fix_links(
        html_output,
        base_url=os.getenv("WP_URL"),
    )
    print(
        f"   kept={link_report['kept']}  "
        f"fixed_redirect={link_report['fixed_redirect']}  "
        f"stripped_broken={link_report['stripped_broken']}  "
        f"stripped_unauthoritative={link_report['stripped_unauthoritative']}  "
        f"stripped_internal_404={link_report['stripped_internal_404']}"
    )

    # ── Step 4: Inject FAQ Section ────────────────────────────────────────────
    print("\n❓ Step 4: Generating FAQ section...")
    html_output = inject_faq_section(html_output, generator.my_llm)

    # ── Step 5: Optimize Image ────────────────────────────────────────────────
    optimized_image_path = local_image_path
    if local_image_path and os.path.exists(local_image_path):
        print("\n🖼️  Step 5: Optimizing image...")
        optimized_image_path = optimize_image(local_image_path)
    else:
        print("\n⚠️  Step 5: No image to optimize")

    print(f"\n✅ Article ready. Image: {optimized_image_path}")

    # ── Step 6: Publish to WordPress ──────────────────────────────────────────
    print("\n📤 Step 6: Publishing to WordPress...")
    if noindex:
        print("⚠️  Publishing with NOINDEX for testing")

    result = process_and_publish(
        html_content=html_output,
        local_image_path=optimized_image_path,
        noindex=noindex,
        min_seo_score=MIN_SEO_SCORE,
        force_publish=force_publish,
    )

    print("\n" + "=" * 60)
    print("✅ Pipeline Complete!")
    print("=" * 60)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEO Article Generation Pipeline")
    parser.add_argument("--noindex", action="store_true", default=True)
    parser.add_argument("--index",   action="store_true")
    parser.add_argument("--force",   action="store_true")
    args = parser.parse_args()

    noindex = not args.index
    run_pipeline(noindex=noindex, force_publish=args.force)