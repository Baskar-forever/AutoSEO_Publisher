import os
import re
import json
import base64
import mimetypes
import requests
from dotenv import load_dotenv
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
# from langchain_google_genai import ChatGoogleGenerativeAI
from article_generater import ArticleGenerator
from utils.auto_categorizer import resolve_category_id


load_dotenv()

# WordPress env variables (example names; ensure your .env has these)
WP_URL = os.getenv("WP_URL")                 # e.g. https://example.com
WP_USER = os.getenv("WP_USER")               # username (or email)
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")  # application password

# LLM configuration (ensure Google credentials are set in env as required by your lib)
# LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
# LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

def slugify(text: str) -> str:
    """
    Simple slugifier: lowercase, ascii-ish, replace non-alnum with hyphens, squeeze hyphens.
    Keeps it safe for WP slugs.
    """
    if not text:
        return "post"
    text = text.strip().lower()
    # Replace non-word characters with hyphen
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    # Trim hyphens
    text = re.sub(r"^-+|-+$", "", text)
    # Limit length
    return text[:65]  # SEO best practice: keep URL slug under 65 characters

def basic_auth_header(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("utf-8")
    return {"Authorization": f"Basic {token}"}

def get_all_internal_links():
    """
    Fetches all internal links from the given base URL."""
    base_url = os.getenv("WP_URL", "https://yourdomain.com/")
    visited = set()
    to_visit = {base_url}
    internal_links = set()

    domain = urlparse(base_url).netloc

    while to_visit:
        url = to_visit.pop()
        if url in visited:
            continue
        visited.add(url)

        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Normalize
            href = urljoin(base_url, href)
            parsed = urlparse(href)
            # Only same domain links
            if parsed.netloc != domain:
                continue
            # Remove fragments, query
            clean = parsed.scheme + "://" + parsed.netloc + parsed.path
            if clean not in internal_links:
                internal_links.add(clean)
                to_visit.add(clean)

        time.sleep(0.5)  # be polite, don’t overload server

    return internal_links

# existing_slugs is fetched lazily inside generate_seo_fields_from_html()
# to avoid a full site crawl on every module import (CI startup cost fix).
_cached_slugs = None  # module-level cache so we only crawl once per process

SEO_SYSTEM_PROMPT_TEMPLATE = """
You are an expert SEO specialist trained in Rank Math and on-page optimization.

Given an article’s HTML content, extract the topic and generate the following SEO outputs.

Output MUST be strict JSON (no extra prose) with these fields:
{{
  "focus_keyword": "...",
  "seo_title": "...",
  "seo_description": "...",
  "url_slug": "..."
}}

Rules:
- **CRITICAL**: Generate 3-4 focus keywords (comma-separated, e.g., "ai technology, machine learning, artificial intelligence").
- Each keyword must be 1-3 words, natural, trending with good search volume.
- Primary keyword (first) MUST appear in: seo_title (at start), seo_description, url_slug, first 100 words.
- All 3-4 keywords should appear throughout title, description, and content.
- Combined keyword density should be ~1.0% across all keywords.
- seo_title length: 45–60 characters. Must contain power words (Amazing, Ultimate, Best, Complete, Proven, Guide) and at least one number (Top 10, 5 Ways, 3 Secrets).
- seo_description length: EXACTLY 120-160 characters. Must contain at least 2 of the focus keywords.
- url_slug: lowercase, hyphen-separated, under 65 characters, contains primary keyword only.
- Do not include HTML tags or entities in title/description.
- Pick high-intent short-tail or mid-tail keywords that complement each other.
- Combined density for all 3-4 keywords should total ~1.0% in overall content.
- Each keyword should appear 3-7 times naturally throughout the article.
- Do not output anything other than the JSON object.

You will be provided with a list of existing URL slugs from the website. 
Before selecting the focus keyword, check whether the same keyword (or a very similar keyword) 
already exists in any of those slugs. 
If yes, DO NOT reuse that keyword. 
Choose a new keyword that is unique compared to all previously used keywords.

If a keyword appears even partially in the slug list (example: "ai-mania" → avoid "ai mania", "ai boom", etc.), 
Existing Slugs:
{slug_list}
you must select a different keyword variant to prevent focus keyword duplication errors in Rank Math.


CRITICAL REMINDERS:
- OUTPUT FORMAT: "focus_keyword": "keyword1, keyword2, keyword3" (3-4 keywords, comma-separated)
- All keywords must be trending with good search volume
- seo_description: 120-160 characters (NOT less than 120)
- seo_title: 45-60 characters with power word + number
- url_slug: under 65 characters, primary keyword only
"""


def validate_and_fix_seo_description(desc: str, focus_keyword: str, llm) -> str:
    MIN_LEN = 120
    MAX_LEN = 160

    def contains_keyword(text):
        return focus_keyword.lower() in text.lower()

    if MIN_LEN <= len(desc) <= MAX_LEN and contains_keyword(desc):
        return desc.strip()

    # Format the messages as a dict for CrewAI
    messages = [
        {"role": "system", "content": "Return ONLY the rewritten description as plain text. No quotes, no conversational filler."},
        {"role": "user", "content": f"""
        Rewrite the following SEO description:
        - Include the focus keyword: "{focus_keyword}"
        - Keep it between {MIN_LEN} and {MAX_LEN} characters
        - Natural language, clear and compelling for search results

        Original:
        \"\"\"{desc}\"\"\"
        """}
    ]

    try:
        # Use official CrewAI .call()
        new_desc = llm.call(messages)
        new_desc = new_desc.strip().strip('"').strip("'")

        if MIN_LEN <= len(new_desc) <= MAX_LEN and contains_keyword(new_desc):
            return new_desc
            
        return (desc[:MAX_LEN].rstrip() + "...")
    except:
        return (desc[:MAX_LEN].rstrip() + "...")


def generate_seo_fields_from_html(llm, html_content: str) -> dict:
    """
    Calls the CrewAI LLM with HTML content and returns a dict with the SEO fields.
    """
    # Lazy-fetch existing slugs once per process (avoids crawl on import)
    global _cached_slugs
    if _cached_slugs is None:
        _cached_slugs = get_all_internal_links()
    prompt = SEO_SYSTEM_PROMPT_TEMPLATE.format(slug_list=_cached_slugs)

    # 1. Format messages EXACTLY as CrewAI/LiteLLM expects: A list of dictionaries.
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Article Content to Analyze:\n{html_content}"}
    ]

    print("➡️ Asking LLM for SEO suggestions...")
    
    # 2. Use the official CrewAI .call() method
    try:
        raw = llm.call(messages)
    except Exception as e:
        print(f"⚠️ CrewAI LLM execution failed: {e}")
        raw = ""

    # 3. Attempt to parse the JSON
    seo = None
    if raw:
        try:
            # If response is exactly JSON
            seo = json.loads(raw)
        except Exception:
            # Try to extract the first {...} block
            m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if m:
                try:
                    seo = json.loads(m.group(0))
                except Exception:
                    seo = None

    # 4. Fallback logic if parsing fails entirely
    if not seo:
        print("⚠️ LLM did not return valid JSON. Building fallback SEO fields.")
        soup = BeautifulSoup(html_content, "html.parser")
        title_tag = soup.find("title")
        h1_tag = soup.find("h1")
        base_title = (title_tag.string if title_tag and title_tag.string else (h1_tag.get_text() if h1_tag else "Untitled Post")).strip()
        fallback_keyword = " ".join(base_title.split()[:3]).lower()
        seo = {
            "focus_keyword": fallback_keyword,
            "seo_title": base_title[:60],
            "seo_description": (soup.find("meta", attrs={"name":"description"}) or {}).get("content", "") or ((" ".join(soup.get_text().split())[:150] + "...") if soup.get_text() else ""),
            "url_slug": slugify(base_title)
        }

    # 5. Ensure fields exist and are strings
    for k in ["focus_keyword", "seo_title", "seo_description", "url_slug"]:
        seo[k] = (seo.get(k) or "").strip()
        
    seo["url_slug"] = slugify(seo["url_slug"] or seo["focus_keyword"] or seo["seo_title"])

    print("✅ SEO fields ready:", seo)
    return seo

def upload_image_to_wordpress(local_image_path: str):
    """
    Upload local image to WP media. Returns (media_id, image_url) or (None, None).
    """
    if not all([WP_URL, WP_USER, WP_APP_PASSWORD]):
        print("❌ WP credentials for image upload not found.")
        return None, None
    if not os.path.exists(local_image_path):
        print(f"❌ Image file not found: {local_image_path}")
        return None, None

    api_url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    headers = basic_auth_header(WP_USER, WP_APP_PASSWORD)

    mime_type, _ = mimetypes.guess_type(local_image_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    try:
        with open(local_image_path, "rb") as f:
            files = {"file": (os.path.basename(local_image_path), f, mime_type)}
            print(f"Uploading image {local_image_path} ...")
            resp = requests.post(api_url, headers=headers, files=files, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("id"), data.get("source_url")
    except requests.exceptions.HTTPError as err:
        print(f"❌ HTTP Error uploading image: {err.response.status_code} - {err.response.text}")
    except Exception as e:
        print(f"❌ Error uploading image: {e}")
    return None, None

def remove_all_images_from_body(html_content: str):
    """
    Remove ALL <img> tags from the article body content.
    This ensures only the featured/cover image is used, preventing duplicates.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Find body tag
    body_tag = soup.find("body")
    if not body_tag:
        # If no body tag, work with whole document
        body_tag = soup
    
    # Remove all img tags and their parent figures if applicable
    for img in body_tag.find_all("img"):
        # Check if img is inside a figure
        parent_figure = img.find_parent("figure")
        if parent_figure:
            parent_figure.decompose()
        else:
            img.decompose()
    
    print("✅ Removed all embedded images from article body (using featured image only)")
    return str(soup)

def replace_local_image_in_html(html_content: str, local_image_path: str, new_image_url: str, remove_image: bool = False):
    """
    Replace occurrences of local_image_path in <img src="..."> inside the body with new_image_url.
    If remove_image=True, removes the image from body content entirely (use when image is featured image).
    Returns (title, body_html_with_replaced_image, original_seo_title, original_seo_description)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    normalized_local = local_image_path.replace("\\", "/").lstrip("./") if local_image_path else ""
    # title extraction
    title_tag = soup.find("title")
    title = title_tag.string.strip() if title_tag and title_tag.string else None
    # read meta description if any
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    seo_description = meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.has_attr("content") else None
    # Find body
    body_tag = soup.find("body")
    if not body_tag:
        # if no body, use whole html as content
        body_html = str(soup)
    else:
        # Find and handle image tags that match the local path
        imgs = body_tag.find_all("img", src=True)
        found = False
        for img in imgs:
            src = img["src"].replace("\\", "/")
            if normalized_local and (normalized_local.endswith(src) or src.endswith(normalized_local) or src == normalized_local):
                if remove_image:
                    # Remove the entire figure/img element to avoid duplicate with featured image
                    parent = img.find_parent("figure")
                    if parent:
                        parent.decompose()
                    else:
                        img.decompose()
                else:
                    img["src"] = new_image_url
                found = True
                break  # Only handle first matching image
        if not found and normalized_local:
            # attempt match by basename
            basename = os.path.basename(normalized_local)
            for img in imgs:
                if os.path.basename(img["src"]) == basename:
                    if remove_image:
                        parent = img.find_parent("figure")
                        if parent:
                            parent.decompose()
                        else:
                            img.decompose()
                    else:
                        img["src"] = new_image_url
                    found = True
                    break
        if found:
            if remove_image:
                print(f"✅ Removed embedded image from body (will use featured image instead)")
            else:
                print(f"✅ Replaced local image placeholder(s) with {new_image_url}")
        else:
            print("⚠️ Could not find matching <img> tag to replace/remove.")
        body_html = "".join(str(child) for child in body_tag.contents).strip()

    return title or "Untitled Post", body_html, title or None, seo_description or None


def post_to_wordpress(title: str, content: str, focus_keyword: str, seo_title: str, seo_description: str, url_slug: str, media_id=None, noindex: bool = False,category_id=None):
    """
    Posts a draft to WordPress, sets Rank Math meta and slug, and optionally attaches featured image.
    Set noindex=True for testing articles before indexing to Google.
    """
    if not all([WP_URL, WP_USER, WP_APP_PASSWORD]):
        print("❌ WordPress credentials (WP_URL, WP_USER, WP_APP_PASSWORD) not found.")
        return None

    api_url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
    headers = basic_auth_header(WP_USER, WP_APP_PASSWORD)
    headers["Content-Type"] = "application/json"

    # Rank Math meta keys - plugin may expect specific meta keys; adjust if needed
    meta_payload = {
        "rank_math_focus_keyword": focus_keyword,
        "rank_math_title": seo_title,
        "rank_math_description": seo_description,
        "_hide_featured_image": "1"
    }
    
    # Add noindex meta for testing (prevents Google indexing)
    if noindex:
        meta_payload["rank_math_robots"] = ["noindex", "nofollow"]
        print("⚠️ Article will be set to NOINDEX (for testing)")

    payload = {
        "title": seo_title,
        "content": content,
        "status": "publish",
        "meta": meta_payload,
        "slug": url_slug
    }
    if media_id:
        payload["featured_media"] = media_id

    

    try:
        print(f"Posting article '{title}' to WordPress...")
        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        print(f"✅ Posted! Post ID: {data.get('id')} Link: {data.get('link')}")
        return data
    except requests.exceptions.HTTPError as err:
        print(f"❌ HTTP Error posting article: {err.response.status_code} - {err.response.text}")
    except Exception as e:
        print(f"❌ Error posting article: {e}")
    return None

def fix_multiple_h1(html_content: str) -> str:
    """
    Remove ALL <h1> tags from HTML body content.
    WordPress already displays the post title outside content,
    so we must avoid duplicate H1 inside the body.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove every H1 in the body
    for h1 in soup.find_all("h1"):
        h1.decompose()

    return str(soup)

def clean_html(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove WordPress header blocks that duplicate the title
    for header in soup.find_all("header"):
        header.decompose()
    
    for h1 in soup.find_all("h1"):
        h1.decompose()

    return str(soup)


def update_media_alt(media_id: int, alt_text: str):
    """
    Update ALT text on uploaded media in WordPress.
    """
    if not media_id:
        return

    api_url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
    headers = basic_auth_header(WP_USER, WP_APP_PASSWORD)
    headers["Content-Type"] = "application/json"

    payload = {
        "alt_text": alt_text.strip()
    }

    try:
        print(f"🔄 Updating ALT text for Media ID {media_id} ...")
        resp = requests.post(api_url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        print("✅ ALT text updated successfully!")
    except Exception as e:
        print(f"⚠️ Failed to update media ALT: {e}")


# ... (Keep everything above wrap_images_in_figure exactly the same) ...

def wrap_images_in_figure(html):
    soup = BeautifulSoup(html, "html.parser")

    # Loop through all <img> tags
    for img in soup.find_all("img"):

        # If already inside a figure.wp-block-image, skip
        if img.parent.name == "figure" and "wp-block-image" in img.parent.get("class", []):
            continue

        # Create <figure class="wp-block-image">
        figure = soup.new_tag("figure", **{"class": "wp-block-image size-large aligncenter"})

        # Move existing <img> into the figure
        img.wrap(figure)

    return str(soup)

# ==================================================================
# NEW: AGENTIC SEO REVISION LOOP FUNCTIONS
# ==================================================================

def auto_fix_seo_meta(llm, current_meta: dict, issues: list) -> dict:
    """Uses the CrewAI LLM to fix SEO title and slug based on validation issues."""
    prompt = f"""
    You are an Expert SEO Editor.
    The current SEO metadata failed validation with these issues:
    {chr(10).join(issues)}

    Current Metadata:
    Title: {current_meta['seo_title']}
    Focus Keyword: {current_meta['focus_keyword']}
    Slug: {current_meta['url_slug']}

    Rules:
    - Ensure Title contains a power word (e.g., Ultimate, Best, Amazing, Proven, Guide).
    - Ensure Title contains a number (e.g., 7 Ways, Top 10).
    - Ensure Title length is between 45 and 60 characters.
    - Ensure Slug is under 65 characters and contains the keyword.
    - DO NOT change the focus keyword itself.

    Return ONLY valid JSON:
    {{
        "seo_title": "...",
        "url_slug": "..."
    }}
    """
    messages = [
        {"role": "system", "content": "You output strict JSON only. No explanations, no markdown blocks."},
        {"role": "user", "content": prompt}
    ]
    print("🔧 Agent fixing SEO Meta (Title/Slug)...")
    try:
        raw = llm.call(messages).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
        
        data = json.loads(raw)
        current_meta["seo_title"] = data.get("seo_title", current_meta["seo_title"])
        if "url_slug" in data:
            current_meta["url_slug"] = slugify(data["url_slug"])
        return current_meta
    except Exception as e:
        print(f"⚠️ Meta auto-fix failed: {e}")
        return current_meta


def auto_fix_seo_html(llm, html_content: str, focus_keyword: str, issues: list) -> str:
    """Uses the CrewAI LLM to rewrite parts of the HTML to fix density, links, and paragraph issues."""
    prompt = f"""
    You are an Expert SEO Editor. 
    The following HTML article failed SEO validation with these specific issues:
    {chr(10).join(issues)}

    Focus Keyword: "{focus_keyword}"

    Please modify the HTML to fix ONLY these issues:
    - If keyword density is too low, naturally weave the focus keyword into existing paragraphs.
    - If keyword density is too high, remove some instances naturally.
    - If focus keyword is not in the first 100 words, update the first paragraph to include it natively.
    - If paragraphs are too long (>120 words), split them into smaller <p> tags.
    - If internal or external links are missing, wrap existing relevant text in <a> tags. 
      (Use href='/blog/...' for internal, and href='https://...' with target='_blank' rel='noopener' for external).

    CRITICAL RULES:
    - RETURN THE ENTIRE HTML DOCUMENT. Do not truncate!
    - DO NOT remove any existing images, Table of Contents (<nav>), or FAQ sections.
    - Output ONLY the raw HTML code. Do not wrap in ```html or include explanations.
    """
    messages = [
        {"role": "system", "content": "You output strictly HTML code, nothing else."},
        {"role": "user", "content": prompt + f"\n\nHTML Content:\n{html_content}"}
    ]
    print("🔧 Agent modifying HTML content to boost SEO density/links...")
    try:
        raw = llm.call(messages).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```html|^```|```$", "", raw, flags=re.MULTILINE).strip()
        return raw
    except Exception as e:
        print(f"⚠️ HTML auto-fix failed: {e}")
        return html_content

# ==================================================================
# MAIN PUBLISHING PIPELINE (UPDATED WITH REVISION LOOP)
# ==================================================================

def process_and_publish(html_content: str, local_image_path: str = None, noindex: bool = False, min_seo_score: int = 80, force_publish: bool = False):
    from utils.seo_validator import validate_seo
    
    llm = ArticleGenerator()

    seo = generate_seo_fields_from_html(llm.my_llm, html_content)
    focus_keyword = seo.get("focus_keyword", "")
    seo_title = seo.get("seo_title", "")
    seo_description = seo.get("seo_description", "")
    url_slug = seo.get("url_slug") or slugify(seo_title or focus_keyword)

    # --- 2. Upload banner image ---
    media_id = None
    new_image_url = None
    if local_image_path:
        import re
        match = re.search(r'(static[/\\]img[/\\][^\s*]+)', local_image_path)
        if match:
            clean_path = match.group(1).replace('*', '').replace('`', '').strip()
            print(f"🔍 Extracted clean image path: {clean_path}")
            media_id, new_image_url = upload_image_to_wordpress(clean_path)
        else:
            media_id, new_image_url = upload_image_to_wordpress(local_image_path.strip())

    # --- 3. Replace/Remove image links inside HTML ---
    title, body_html, orig_seo_title, orig_seo_desc = replace_local_image_in_html(
        html_content,
        local_image_path or "",
        new_image_url or "",
        remove_image=bool(media_id)
    )

    # Select final SEO metadata
    final_seo_title = seo_title or orig_seo_title or title
    final_seo_description = seo_description or orig_seo_desc or ""
    final_seo_description = validate_and_fix_seo_description(
            final_seo_description, focus_keyword, llm.my_llm
        )
    final_slug = slugify(url_slug or final_seo_title or title)

    # --- 4. SAFE BeautifulSoup processing ---
    soup = BeautifulSoup(body_html, "html.parser")
    html_tag = soup.find("html")
    if not html_tag:
        new_html = soup.new_tag("html")
        body_wrapper = soup.new_tag("body")
        body_wrapper.append(soup)
        new_html.append(body_wrapper)
        soup = BeautifulSoup(str(new_html), "html.parser")
        html_tag = soup.find("html")

    head_tag = soup.find("head")
    if not head_tag:
        head_tag = soup.new_tag("head")
        html_tag.insert(0, head_tag)

    body_tag = soup.find("body")
    if not body_tag:
        body_tag = soup.new_tag("body")
        html_tag.append(body_tag)

    final_html = str(soup)
    final_html = wrap_images_in_figure(final_html)
    
    if media_id:
        final_html = remove_all_images_from_body(final_html)
        print("✅ Using featured image only, all body images removed")

    soup = BeautifulSoup(final_html, "html.parser")
    if media_id and focus_keyword:
        update_media_alt(media_id, focus_keyword)
        for img in soup.find_all("img"):
            img['alt'] = focus_keyword

    final_html = fix_multiple_h1(final_html)
    final_html = str(soup)
    final_html = clean_html(final_html)
    soup = BeautifulSoup(final_html, "html.parser")
    final_html = str(soup)

    # ==================================================================
    # 5. SEO VALIDATION & AGENTIC AUTO-FIX LOOP
    # ==================================================================
    MAX_RETRIES = 2
    current_html = final_html
    current_seo_title = final_seo_title
    current_slug = final_slug
    
    print("\n📊 Validating Initial SEO score...")
    
    for attempt in range(MAX_RETRIES + 1):
        seo_result = validate_seo(current_html, focus_keyword, current_seo_title, current_slug)
        
        # Target accepted: if score >= min_seo_score (e.g., 80 or 85 based on your main.py config)
        if seo_result["score"] >= min_seo_score:
            print(f"\n✅ Target SEO score reached: {seo_result['score']}/100")
            break
            
        if attempt < MAX_RETRIES:
            print(f"\n⚠️ Score is {seo_result['score']}. Initiating Re-evaluation Loop (Attempt {attempt + 1}/{MAX_RETRIES})...")
            issues = seo_result["issues"]
            
            # Check if Meta Title/Slug needs fixing
            meta_issues = [i for i in issues if "title" in i.lower() or "slug" in i.lower()]
            if meta_issues:
                meta_payload = {"seo_title": current_seo_title, "focus_keyword": focus_keyword, "url_slug": current_slug}
                fixed_meta = auto_fix_seo_meta(llm.my_llm, meta_payload, meta_issues)
                current_seo_title = fixed_meta["seo_title"]
                current_slug = fixed_meta["url_slug"]
                
            # Check if HTML needs fixing (Links, Density, Paragraphs)
            html_issues = [i for i in issues if "title" not in i.lower() and "slug" not in i.lower()]
            if html_issues:
                current_html = auto_fix_seo_html(llm.my_llm, current_html, focus_keyword, html_issues)
                current_html = fix_multiple_h1(current_html) # Ensure no duplicate H1s sneak back in
        else:
            if not force_publish:
                print(f"\n❌ Final SEO Score {seo_result['score']} is still below target {min_seo_score} after {MAX_RETRIES} attempts.")
                print("Use --force to publish anyway, or check the article manually.")
                return {
                    "seo": seo,
                    "seo_validation": seo_result,
                    "media_id": media_id,
                    "post": None,
                    "status": "blocked_by_seo"
                }
            
    category_id = resolve_category_id(
        title=title,
        focus_keyword=focus_keyword,
        html_content=current_html,
        llm=llm.my_llm,
    )

    # --- 6. Publish Final Validated Version ---
    posted = post_to_wordpress(
        title=title,
        content=current_html,
        focus_keyword=focus_keyword,
        seo_title=current_seo_title,
        seo_description=final_seo_description,
        url_slug=current_slug,
        media_id=media_id,
        noindex=noindex,
        category_id=category_id
    )

    # Update the returned SEO dict with any fixed values
    seo["seo_title"] = current_seo_title
    seo["url_slug"] = current_slug

    return {
        "seo": seo,
        "seo_validation": seo_result,
        "media_id": media_id,
        "post": posted,
        "status": "published" if posted else "failed"
    }