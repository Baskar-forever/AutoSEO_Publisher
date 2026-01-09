# tools/serp_tool.py
from crewai.tools import tool
import requests
import os
from dotenv import load_dotenv
load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

@tool("serper_fetch_tool")
def serper_fetch_tool(query: str):
    """
    Fetches recent Google search results using the Serper.dev API.
    Returns top 5 snippets with title, snippet, and URL.
    """
    try:
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": 5}
        response = requests.post("https://google.serper.dev/search", headers=headers, json=payload)

        if response.status_code != 200:
            return f"Error: Serper API returned status {response.status_code}: {response.text}"

        data = response.json()
        results = data.get("organic", [])
        if not results:
            return "No search results found."

        summaries = [
            f"{i+1}. {r.get('title')}\n{r.get('snippet', 'No snippet available')}\n{r.get('link')}"
            for i, r in enumerate(results[:5])
        ]
        return "\n\n".join(summaries)

    except Exception as e:
        return f"Error fetching articles: {e}"
