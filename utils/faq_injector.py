import json
from bs4 import BeautifulSoup

FAQ_SYSTEM_PROMPT = """
You are an SEO expert.

From the given article HTML, generate 3 to 5 FAQs that:
- Are directly answered by the article
- Match real user search intent
- Use simple, factual language
- Avoid speculation or promises

Return ONLY valid JSON in this format:

{
  "faqs": [
    {
      "question": "What is ...?",
      "answer": "..."
    }
  ]
}

Rules:
- No markdown
- No explanations
- No extra keys
- Questions must start with:
  "What is", "How does", or "Is it worth"
"""

def generate_faqs_with_llm(llm, html_content: str) -> list:
    response = llm.invoke([
        ("system", FAQ_SYSTEM_PROMPT),
        ("human", html_content)
    ])

    raw = response.content.strip()

    try:
        data = json.loads(raw)
        return data.get("faqs", [])
    except Exception:
        return []


def inject_faq_section(html: str, llm):
    soup = BeautifulSoup(html, "html.parser")

    faqs = generate_faqs_with_llm(llm, html)

    if not faqs:
        return html  # Fail-safe: do nothing

    # -------------------------
    # 1. Visible FAQ HTML
    # -------------------------
    faq_section = soup.new_tag("section", id="faq")

    h2 = soup.new_tag("h2")
    h2.string = "Frequently Asked Questions"
    faq_section.append(h2)

    for faq in faqs:
        q = soup.new_tag("h3")
        q.string = faq["question"]

        a = soup.new_tag("p")
        a.string = faq["answer"]

        faq_section.append(q)
        faq_section.append(a)

    body = soup.find("body")
    if body:
        body.append(faq_section)

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": []
    }

    for faq in faqs:
        faq_schema["mainEntity"].append({
            "@type": "Question",
            "name": faq["question"],
            "acceptedAnswer": {
                "@type": "Answer",
                "text": faq["answer"]
            }
        })

    script = soup.new_tag("script", type="application/ld+json")
    script.string = json.dumps(faq_schema, ensure_ascii=False)

    if body:
        body.append(script)

    return str(soup)
