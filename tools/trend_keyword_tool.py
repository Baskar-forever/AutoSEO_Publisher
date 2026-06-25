import requests
import os
from datetime import datetime
from crewai.tools import tool
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

TOOL_ARGS_SCHEMA = {
    "type": "object",
    "properties": {
        "dummy_arg": {
            "type": "string",
            "description": "Dummy argument to satisfy strict API schema requirements.",
            "default": "dummy"
        }
    },
    "required": []
}

# Module-level cache — injected by main.py before the crew runs
_exclusion_brief: str = ""

def set_exclusion_brief(brief: str):
    """Called by main.py after fetching published topics."""
    global _exclusion_brief
    _exclusion_brief = brief


@tool("Trend Keyword Tool")
def trend_keyword_tool(dummy_arg: str = "dummy"):
    """
    Find trending tech topics using Serper.dev (Google Search API).
    Always searches for CURRENT topics and avoids previously published ones.
    Returns a concise list of trending article-worthy topics.
    """
    current_year  = datetime.now().year
    current_month = datetime.now().strftime("%B %Y")   # e.g. "June 2026"

    try:
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }

        # Search with current date context so results are fresh
        queries = [
            f"trending tech news {current_month}",
            f"latest AI technology news {current_year}",
            f"top technology stories this week {current_year}",
        ]

        topics = set()

        for query in queries:
            payload = {"q": query, "num": 10, "tbs": "qdr:w"}  # tbs=qdr:w = last week
            try:
                resp = requests.post(
                    "https://google.serper.dev/search",
                    json=payload,
                    headers=headers,
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"⚠️ Serper query failed for '{query}': {e}")
                continue

            # From organic results
            for item in data.get("organic", []):
                title   = item.get("title", "").split("|")[0].strip()
                snippet = item.get("snippet", "")
                date    = item.get("date", "")

                if not title:
                    continue

                # Hard-skip results that mention old years
                years_in = [int(y) for y in
                            __import__("re").findall(r"\b(20\d{2})\b", title + snippet)]
                if years_in and max(years_in) < current_year:
                    continue

                topics.add(f"{title} [{date}]" if date else title)

            # People Also Ask
            for q in data.get("peopleAlsoAsk", []):
                question = q.get("question", "")
                if question:
                    topics.add(question)

            # Related Searches
            for rel in data.get("relatedSearches", []):
                q = rel.get("query", "")
                if q:
                    topics.add(q)

        if not topics:
            return [f"Fallback: Emerging AI tools {current_year}"]

        topics_list = list(topics)[:15]

        # Prepend the exclusion brief so the LLM sees what to avoid
        output_parts = []
        if _exclusion_brief:
            output_parts.append(_exclusion_brief)
            output_parts.append("")
        output_parts.append(f"⚠️  IMPORTANT: Only suggest topics from {current_year}. "
                            f"Do NOT suggest topics covered in the exclusion list above.")
        output_parts.append(f"\n🔥 Currently trending topics ({current_month}):")
        output_parts.extend([f"  - {t}" for t in topics_list])

        result = "\n".join(output_parts)
        print(result)
        return result

    except Exception as e:
        print("⚠️ TrendKeywordTool Error:", e)
        return [f"Fallback: Future of AI and automation {current_year}"]


try:
    trend_keyword_tool.args = TOOL_ARGS_SCHEMA
except Exception:
    pass