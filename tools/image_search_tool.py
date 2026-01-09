import os
import requests
import mimetypes
from crewai.tools import tool
from dotenv import load_dotenv
load_dotenv()


@tool("image_search_tool")
def image_search_tool(keyword: str):
    """
    Searches and downloads a relevant image for a given keyword using Serper.dev (Google Images API).
    Saves the first valid image locally under static/img/.
    Returns the saved file path.
    """
    SERPER_API_KEY = os.getenv("SERPER_API_KEY", None)
    if not SERPER_API_KEY:
        return "❌ SERPER_API_KEY not found. Please set it as an environment variable."

    try:
        save_dir = os.path.join("static", "img")
        os.makedirs(save_dir, exist_ok=True)

        # Serper.dev Images API endpoint
        url = "https://google.serper.dev/images"
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {"q": keyword, "num": 6}

        print(f"🔍 Searching images for: {keyword}")
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        images = data.get("images", [])
        if not images:
            return "⚠️ No images found."

        headers_img = {"User-Agent": "Mozilla/5.0"}
        for img in images:
            image_url = img.get("imageUrl") or img.get("thumbnailUrl")
            if not image_url:
                continue

            try:
                r = requests.get(image_url, stream=True, timeout=15, headers=headers_img)
                if not r.ok:
                    continue

                content_type = r.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    continue

                ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".jpg"
                if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
                    ext = ".jpg"

                safe = "".join(
                    c for c in keyword.replace(" ", "_") if c.isalnum() or c in ("_", "-")
                )
                path = os.path.join(save_dir, f"{safe}{ext}")

                with open(path, "wb") as f:
                    for chunk in r.iter_content(1024):
                        if chunk:
                            f.write(chunk)

                if os.path.getsize(path) < 2048:  # skip broken images
                    os.remove(path)
                    continue

                print("✅ Image saved:", path)
                return path

            except Exception:
                continue

        return "⚠️ All image downloads failed."

    except Exception as e:
        return f"❌ Image search failed: {e}"
