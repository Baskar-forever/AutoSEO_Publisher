# main.py  —  Full SEO Article Generation & WordPress Publishing Pipeline
"""
Integrates: Article generation, image optimization, SEO validation,
FAQ injection, Table of Contents, and noindex control for testing.

Change log (link-audit hardening):
  - audit_and_fix_links now returns (html, report) — consumed here.
  - WP_URL passed explicitly so the auditor resolves relative hrefs correctly.
  - Link stats printed after audit step.
"""
import os
import argparse
from dotenv import load_dotenv
from article_generater import ArticleGenerator
from utils.link_audit import audit_and_fix_links
from utils.faq_injector import inject_faq_section
from utils.image_optimizer import optimize_image
from utils.toc_generator import inject_toc
from wordpress_uploader import upload_image_to_wordpress, process_and_publish

load_dotenv()

MIN_SEO_SCORE = 80


def run_pipeline(noindex: bool = True, force_publish: bool = False):
    print("=" * 60)
    print("🚀 Starting Full SEO Article Generation Pipeline")
    print("=" * 60)

    # Step 1: Generate Article
    print("\n📝 Step 1: Generating article content...")
    generator = ArticleGenerator()
    html_output, local_image_path = generator.generate_article()

    if not html_output:
        print("❌ Article generation failed. Exiting.")
        return None

    # Step 2: Inject Table of Contents  ← MOVED before link audit
    # TOC must run first so fragment hrefs (#section-id) exist in the DOM
    # before the link auditor evaluates them.
    print("\n📑 Step 2: Generating Table of Contents...")
    html_output = inject_toc(html_output)

    # Step 3: Audit and Fix Links
    print("\n🔗 Step 3: Auditing and fixing links...")
    html_output, link_report = audit_and_fix_links(
        html_output,
        base_url=os.getenv("WP_URL"),   # explicit — avoids env-miss silently
    )
    print(
        f"   kept={link_report['kept']}  "
        f"fixed_redirect={link_report['fixed_redirect']}  "
        f"stripped_broken={link_report['stripped_broken']}  "
        f"stripped_unauthoritative={link_report['stripped_unauthoritative']}  "
        f"stripped_internal_404={link_report['stripped_internal_404']}"
    )

    # Step 4: Inject FAQ Section
    print("\n❓ Step 4: Generating FAQ section...")
    html_output = inject_faq_section(html_output, generator.my_llm)

    # Step 5: Optimize Image
    optimized_image_path = local_image_path
    if local_image_path and os.path.exists(local_image_path):
        print("\n🖼️  Step 5: Optimizing image...")
        optimized_image_path = optimize_image(local_image_path)
    else:
        print("\n⚠️  Step 5: No image to optimize")

    print(f"\n✅ Article generated. Image: {optimized_image_path}")

    # Step 6: Publish to WordPress
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
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    noindex = not args.index
    run_pipeline(noindex=noindex, force_publish=args.force)