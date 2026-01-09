import os
import requests
import mimetypes
from crewai.tools import tool
from dotenv import load_dotenv
from PIL import Image  # Requires: pip install Pillow
from io import BytesIO

load_dotenv()

@tool("image_search_tool")
def image_search_tool(keyword: str):
    """
    Searches, downloads, AND OPTIMIZES an image for the keyword.
    Converts to WebP to meet SEO Roadmap requirements.
    """
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", None)
    if not SERPER_API_KEY:
        return "❌ SERPER_API_KEY not found."

    try:
        save_dir = os.path.join("static", "img")
        os.makedirs(save_dir, exist_ok=True)

        url = "https://google.serper.dev/images"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        payload = {"q": keyword, "num": 6}

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        data = resp.json()
        images = data.get("images", [])

        if not images:
            return "⚠️ No images found."

        headers_img = {"User-Agent": "Mozilla/5.0"}
        
        for img in images:
            image_url = img.get("imageUrl")
            if not image_url: continue

            try:
                r = requests.get(image_url, stream=True, timeout=10, headers=headers_img)
                if r.status_code == 200:
                    # OPTIMIZATION STEP
                    img_obj = Image.open(BytesIO(r.content))
                    
                    # Convert to RGB if necessary
                    if img_obj.mode in ("RGBA", "P"):
                        img_obj = img_obj.convert("RGB")

                    # Create filename
                    safe_name = "".join(c for c in keyword.replace(" ", "_") if c.isalnum() or c in "_-")
                    filename = f"{safe_name}.webp"
                    path = os.path.join(save_dir, filename)

                    # Save as optimized WebP (Quality 80 is standard for SEO)
                    img_obj.save(path, "WEBP", quality=80, optimize=True)

                    print(f"✅ Image optimized & saved: {path}")
                    return path
            except Exception as e:
                print(f"Failed to process image {image_url}: {e}")
                continue

        return "⚠️ All image downloads failed."

    except Exception as e:
        return f"❌ Image search failed: {e}"