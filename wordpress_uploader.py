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
from langchain_google_genai import ChatGoogleGenerativeAI

# Update this path if necessary
ENV_PATH = "d:\\SEOarticleGeneration\\.env"
load_dotenv(dotenv_path=ENV_PATH)

# WordPress env variables (example names; ensure your .env has these)
WP_URL = os.getenv("WP_URL")                 # e.g. https://example.com
WP_USER = os.getenv("WP_USER")               # username (or email)
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")  # application password

# LLM configuration (ensure Google credentials are set in env as required by your lib)
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

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
    return text[:120]

def basic_auth_header(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("utf-8")
    return {"Authorization": f"Basic {token}"}

def get_all_internal_links():
    """
    Fetches all internal links from the given base URL."""
    base_url = "https://readtechflow.com/"
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

existing_slugs = get_all_internal_links()
SEO_SYSTEM_PROMPT = f"""
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
- Focus keyword MUST appear in seo_title, seo_description, and url_slug.Focus keyword should be have 1.0 density in overall content.
- seo_title length: 45–60 characters (aim inside this range).Title should contain power words like Amazing, Ultimate, Best, Complete, Proven, Guide etc., and at least one number like Top 10, 5 Ways, 3 Secrets etc.,
- seo_description length: 120 characters.Make it sure does it contains 120  characters.
- url_slug should be lowercase, hyphen-separated, short, readable and contain the focus keyword (no stop characters).It length should be under 65 characters.
- Do not include HTML tags or entities in title/description.
- If multiple keyword choices exist, pick the highest intent short-tail or mid-tail keyword.
- Keep focus keyword short (1–4) and natural.That keyword should be in trend and have good search volume.2 or 3 keywords with comma separated.TO increase the SEO score.That 2 or 3 keywords should be in the title and description and url.
- Keeps focus keyword density 1.0 in overall content.
- keep seo_description length 120 characters or less
- Do not output anything other than the JSON object.

You will be provided with a list of existing URL slugs from the website. 
Before selecting the focus keyword, check whether the same keyword (or a very similar keyword) 
already exists in any of those slugs. 
If yes, DO NOT reuse that keyword. 
Choose a new keyword that is unique compared to all previously used keywords.

If a keyword appears even partially in the slug list (example: "ai-mania" → avoid "ai mania", "ai boom", etc.), 
Existing Slugs:
{existing_slugs}
you must select a different keyword variant to prevent focus keyword duplication errors in Rank Math.


Mind it your are master security specialist and also expert in on page SEO and Rank Math plugin for wordpress.So you are the responsible high quality focus keywords 1-4 and description 120 characters or less and seo title 45-60 characters and slug under 65 characters.
Dont forget check this. MInd it focus keyword should be in trend and have good search volume.
"""


def validate_and_fix_seo_description(desc: str, focus_keyword: str, llm) -> str:
    """
    Ensures the SEO description length is between 120–160 characters
    and contains the focus keyword. Regenerates via LLM if needed.
    """
    MIN_LEN = 120
    MAX_LEN = 160

    def contains_keyword(text):
        return focus_keyword.lower() in text.lower()

    # Already valid — return as is
    if MIN_LEN <= len(desc) <= MAX_LEN and contains_keyword(desc):
        return desc.strip()

    # Build regeneration request
    regen_prompt = f"""
        Rewrite the following SEO description:
        - Include the focus keyword: "{focus_keyword}"
        - Keep it between {MIN_LEN} and {MAX_LEN} characters
        - Natural language, no quotes, no brackets
        - Clear and compelling for search results

        Original:
        \"\"\"{desc}\"\"\"
        """

    try:
        regen_msg = llm.invoke([
            ("system", "Return ONLY the rewritten description as plain text."),
            ("human", regen_prompt)
        ])
        new_desc = regen_msg.content.strip()

        # Final strict validation
        if MIN_LEN <= len(new_desc) <= MAX_LEN and contains_keyword(new_desc):
            return new_desc

        # Fallback soft trim
        return (desc[:MAX_LEN].rstrip() + "...")

    except:
        # Backup final fallback
        return (desc[:MAX_LEN].rstrip() + "...")


def generate_seo_fields_from_html(llm, html_content: str) -> dict:
    """
    Calls the LLM with HTML content and returns a dict with the SEO fields.
    Returns fallback values if LLM fails.
    """

    
    messages = [
        ("system", SEO_SYSTEM_PROMPT),
        ("human", html_content)
    ]

    print("➡️ Asking LLM for SEO suggestions...")
    # Using llm.invoke pattern from your example
    ai_msg = llm.invoke(messages)
    raw = ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)

    # Try to locate JSON substring in response in case LLM adds commentary (shouldn't)
    try:
        # If response is exactly JSON
        seo = json.loads(raw)

    except Exception:
        # try to extract the first {...} block
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if m:
            try:
                seo = json.loads(m.group(0))
            except Exception:
                seo = None
        else:
            seo = None

    if not seo:
        print("⚠️ LLM did not return valid JSON. Building fallback SEO fields.")
        # Fallback: extract title from HTML <title> or h1 and build simple fields
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
    # Ensure fields exist and are strings
    for k in ["focus_keyword", "seo_title", "seo_description", "url_slug"]:
        seo[k] = (seo.get(k) or "").strip()
    # sanitize slug if LLM produced odd chars
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

def replace_local_image_in_html(html_content: str, local_image_path: str, new_image_url: str):
    """
    Replace occurrences of local_image_path in <img src="..."> inside the body with new_image_url.
    Returns (title, body_html_with_replaced_image, original_seo_title, original_seo_description)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    normalized_local = local_image_path.replace("\\", "/").lstrip("./")
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
        # replace image tags that match the local path
        imgs = body_tag.find_all("img", src=True)
        found = False
        for img in imgs:
            src = img["src"].replace("\\", "/")
            if normalized_local.endswith(src) or src.endswith(normalized_local) or src == normalized_local:
                img["src"] = new_image_url
                found = True
        if not found:
            # attempt match by basename
            basename = os.path.basename(normalized_local)
            for img in imgs:
                if os.path.basename(img["src"]) == basename:
                    img["src"] = new_image_url
                    found = True
        if found:
            print(f"✅ Replaced local image placeholder(s) with {new_image_url}")
        else:
            print("⚠️ Could not find matching <img> tag to replace.")
        body_html = "".join(str(child) for child in body_tag.contents).strip()

    return title or "Untitled Post", body_html, title or None, seo_description or None


def post_to_wordpress(title: str, content: str, focus_keyword: str, seo_title: str, seo_description: str, url_slug: str, media_id=None):
    """
    Posts a draft to WordPress, sets Rank Math meta and slug, and optionally attaches featured image.
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

    payload = {
        "title": seo_title,
        "content": content,
        "status": "draft",
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


def process_and_publish(html_content: str, local_image_path: str = None):
    """
    Full pipeline:
    1. Generate SEO fields via LLM
    2. Upload image (optional)
    3. Replace image in HTML body
    4. Insert CSS into <head>
    5. Remove <h1>
    6. Post to WP with RankMath fields
    """

    llm = ChatGoogleGenerativeAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=None,
        timeout=None,
        max_retries=2
    )

    seo = generate_seo_fields_from_html(llm, html_content)
    focus_keyword = seo.get("focus_keyword", "")
    seo_title = seo.get("seo_title", "")
    seo_description = seo.get("seo_description", "")
    url_slug = seo.get("url_slug") or slugify(seo_title or focus_keyword)

    # --- 2. Upload banner image ---
    media_id = None
    new_image_url = None
    if local_image_path:
        media_id, new_image_url = upload_image_to_wordpress(local_image_path)

    # --- 3. Replace image links inside HTML ---
    title, body_html, orig_seo_title, orig_seo_desc = replace_local_image_in_html(
        html_content,
        local_image_path or "",
        new_image_url or ""
    )

    # Select final SEO metadata
    final_seo_title = seo_title or orig_seo_title or title
    final_seo_description = seo_description or orig_seo_desc or ""
    final_seo_description = validate_and_fix_seo_description(
            final_seo_description,
            focus_keyword,
            llm
        )
    final_slug = slugify(url_slug or final_seo_title or title)

    # --- 4. SAFE BeautifulSoup processing ---
    soup = BeautifulSoup(body_html, "html.parser")

    # Ensure <html> exists
    html_tag = soup.find("html")
    if not html_tag:
        new_html = soup.new_tag("html")

        body_wrapper = soup.new_tag("body")
        body_wrapper.append(soup)

        new_html.append(body_wrapper)
        soup = BeautifulSoup(str(new_html), "html.parser")
        html_tag = soup.find("html")

    # Ensure <head> exists
    head_tag = soup.find("head")
    if not head_tag:
        head_tag = soup.new_tag("head")
        html_tag.insert(0, head_tag)

    # Ensure <body> exists
    body_tag = soup.find("body")
    if not body_tag:
        body_tag = soup.new_tag("body")
        html_tag.append(body_tag)


    final_html = str(soup)

    final_html = wrap_images_in_figure(final_html)

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

    posted = post_to_wordpress(
        title=title,
        content=final_html,
        focus_keyword=focus_keyword,
        seo_title=final_seo_title,
        seo_description=final_seo_description,
        url_slug=final_slug,
        media_id=media_id
    )

    return {
        "seo": seo,
        "media_id": media_id,
        "post": posted
    }
