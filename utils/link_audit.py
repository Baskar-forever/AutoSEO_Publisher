import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

AUTHORITY_DOMAINS = [
    "medium.com",
    "reddit.com",
    "developer.mozilla.org",
    "stackoverflow.com",
    "github.com",
    "wikipedia.org",
    "google.com",
    "openai.com",
    "news.ycombinator.com"
]

TIMEOUT = 8

def is_authoritative(url: str) -> bool:
    return any(domain in url for domain in AUTHORITY_DOMAINS)

def check_url(url: str):
    try:
        r = requests.head(url, allow_redirects=True, timeout=TIMEOUT)
        return r.status_code, r.url
    except:
        return None, None

def audit_and_fix_links(html: str, base_url="https://readtechflow.com"):
    soup = BeautifulSoup(html, "html.parser")
    site_domain = urlparse(base_url).netloc

    for a in soup.find_all("a", href=True):
        original_href = a["href"]
        full_url = urljoin(base_url, original_href)
        parsed = urlparse(full_url)

        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        status, final_url = check_url(clean_url)

        is_internal = site_domain in clean_url

        # ❌ Broken link
        if status is None or status >= 400:
            a.unwrap()
            continue

        # 🔁 Redirect → replace with final URL
        if final_url and final_url != clean_url:
            clean_url = final_url

        # 🌍 External link rules
        if not is_internal:
            if not is_authoritative(clean_url):
                a.unwrap()
                continue

            a["href"] = clean_url
            a["rel"] = "noopener"
            a["target"] = "_blank"

        # 🏠 Internal link rules
        else:
            a["href"] = clean_url

    return str(soup)
