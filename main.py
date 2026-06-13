# main.py
"""
Full SEO Article Generation & WordPress Publishing Pipeline
Integrates: Article generation, image optimization, SEO validation,
FAQ injection, Table of Contents, and noindex control for testing.
"""
import os
import argparse
from dotenv import load_dotenv
from article_generater import ArticleGenerator
from utils.link_audit import audit_and_fix_links
from utils.faq_injector import inject_faq_section
from utils.image_optimizer import optimize_image
# from utils.seo_validator import validate_seo
from utils.toc_generator import inject_toc
from wordpress_uploader import upload_image_to_wordpress, process_and_publish
# from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# LLM configuration
# LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
# LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# SEO configuration
MIN_SEO_SCORE = 80  # Minimum score to publish (without noindex)


def run_pipeline(noindex: bool = True, force_publish: bool = False):
    """
    Run the full article generation pipeline.
    
    Args:
        noindex: If True, publish with noindex (for testing). Default True for safety.
        force_publish: If True, publish even if SEO score is below threshold.
    """
    print("=" * 60)
    print("🚀 Starting Full SEO Article Generation Pipeline")
    print("=" * 60)
    
    # ═══════════════════════════════════════════════════════════
    # Step 1: Generate Article
    # ═══════════════════════════════════════════════════════════
    print("\n📝 Step 1: Generating article content...")
    generator = ArticleGenerator()
    html_output, local_image_path = generator.generate_article()
    
    if not html_output:
        print("❌ Article generation failed. Exiting.")
        return None
    
    # ═══════════════════════════════════════════════════════════
    # Step 2: Audit and Fix Links
    # ═══════════════════════════════════════════════════════════
    print("\n🔗 Step 2: Auditing and fixing links...")
    html_output = audit_and_fix_links(html_output)
    
    # ═══════════════════════════════════════════════════════════
    # Step 3: Inject Table of Contents
    # ═══════════════════════════════════════════════════════════
    print("\n📑 Step 3: Generating Table of Contents...")
    html_output = inject_toc(html_output)
    
    # ═══════════════════════════════════════════════════════════
    # Step 4: Inject FAQ Section
    # ═══════════════════════════════════════════════════════════
    print("\n❓ Step 4: Generating FAQ section...")
    # faq_llm = ChatGoogleGenerativeAI(
    #     model=LLM_MODEL,
    #     temperature=LLM_TEMPERATURE,
    #     max_tokens=None,
    #     timeout=None,
    #     max_retries=2
    # )
    html_output = inject_faq_section(html_output, generator.my_llm)
    
    # ═══════════════════════════════════════════════════════════
    # Step 5: Optimize Image
    # ═══════════════════════════════════════════════════════════
    optimized_image_path = local_image_path
    if local_image_path and os.path.exists(local_image_path):
        print("\n🖼️ Step 5: Optimizing image...")
        optimized_image_path = optimize_image(local_image_path)
    else:
        print("\n⚠️ Step 5: No image to optimize")
    
    print(f"\n✅ Article generated. Image: {optimized_image_path}")
    
    # ═══════════════════════════════════════════════════════════
    # Step 6: Publish to WordPress
    # ═══════════════════════════════════════════════════════════
    print("\n📤 Step 6: Publishing to WordPress...")
    
    if noindex:
        print("⚠️ Publishing with NOINDEX for testing")
    
    result = process_and_publish(
        html_content=html_output,
        local_image_path=optimized_image_path,
        noindex=noindex,
        min_seo_score=MIN_SEO_SCORE,
        force_publish=force_publish
    )
    
    print("\n" + "=" * 60)
    print("✅ Pipeline Complete!")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEO Article Generation Pipeline")
    parser.add_argument(
        "--noindex", 
        action="store_true", 
        default=True,
        help="Publish with noindex meta (for testing, default: True)"
    )
    parser.add_argument(
        "--index", 
        action="store_true",
        help="Publish with index (allow Google indexing)"
    )
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Force publish even if SEO score is below threshold"
    )
    
    args = parser.parse_args()
    
    # Determine noindex status
    noindex = not args.index  # Default to noindex unless --index is specified
    
    run_pipeline(noindex=noindex, force_publish=args.force)