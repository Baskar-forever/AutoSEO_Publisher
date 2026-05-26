import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import time
from crewai.tools import tool


TOOL_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "dummy_arg": {"type": "string", "description": "Dummy argument to satisfy strict API schema requirements.", "default": "dummy"}
    },
    "required": []
}


@tool("Fetch Internal Links Tool")
def get_all_internal_links(dummy_arg: str = "dummy"):
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


# Attach JSON schema to the tool function object so the tool registry can see inputs
try:
    get_all_internal_links.args = TOOL_ARGS_SCHEMA
except Exception:
    pass