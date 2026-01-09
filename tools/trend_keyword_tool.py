import requests
import os
from crewai.tools import tool
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

@tool("trend_keyword_tool")
def trend_keyword_tool():
    """
    Find trending tech topics using Serper.dev (Google Search API).
    Returns a concise list of trending article-worthy topics.
    """
    try:
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }

        payload = {"q": "trending tech news"}
        response = requests.post("https://google.serper.dev/search", json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()


        topics = set()

        # From organic titles/snippets
        for item in data.get("organic", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            if title:
                topics.add(title.split("|")[0].strip())
            if "AI" in snippet or "technology" in snippet or "startup" in snippet:
                topics.add(snippet[:90].strip() + "...")

        # From People Also Ask
        for q in data.get("peopleAlsoAsk", []):
            question = q.get("question", "")
            if question:
                topics.add(question)

        # From Related Searches
        for rel in data.get("relatedSearches", []):
            q = rel.get("query", "")
            if q:
                topics.add(q)

        if not topics:
            return ["Fallback: Emerging AI tools 2025"]

        # Return top 5 cleaned topics
        topics_list = list(topics)[:5]
        print("🔥 Trending topics found:", topics_list)
        return topics_list

    except Exception as e:
        print("⚠️ TrendKeywordTool Error:", e)
        return ["Fallback: Future of AI and automation"]
