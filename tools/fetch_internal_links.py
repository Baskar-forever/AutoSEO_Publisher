import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
from crewai.tools import tool

@tool("fetch_internal_links")
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