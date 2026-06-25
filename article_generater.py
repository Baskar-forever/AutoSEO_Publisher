import os
from dotenv import load_dotenv
from crewai import Agent , Task , Crew ,LLM

import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda msg: msg

load_dotenv()
from tools.trend_keyword_tool import trend_keyword_tool
from tools.serp_tool import serper_fetch_tool
from tools.image_search_tool import image_search_tool
from tools.fetch_internal_links import get_all_internal_links

    
KEY = os.getenv("OPENAI_API_KEY")
MODEL=os.getenv("MODEL")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
WP_URL = os.getenv("WP_URL", "https://yourwebsite.com")

class ArticleGenerator:
    def __init__(self):
        # self.my_llm = LLM(
        #         api_key=KEY,
        #         model="gemini/gemini-2.5-flash",
        #     )
        
        self.my_llm = LLM(
            api_key=KEY,
            model=MODEL,
            temperature=0.1
         )

    def trend_resarcher_agent(self):
        import random
        # Rotate content genres so every article has a different flavour.
        # The LLM picks ONE topic from the chosen genre — keeping the blog fresh.
        GENRE_WHEEL = [
            # Genre label : what to tell the researcher
            ("AI Deep-Dive",
             "Pick a specific, surprising or controversial AI story from the last 7 days "
             "(e.g. a model beating humans at a new task, a company pivot, a leaked benchmark). "
             "Avoid generic 'AI is transforming X' angles."),

            ("Funny / WTF Tech",
             "Find a genuinely funny, absurd, or unbelievable tech story from this week — "
             "a product fail, a viral bug, an eccentric startup idea, or a tech CEO meme moment. "
             "Tone should be witty and entertaining, not dry."),

            ("Startup & Money",
             "Pick a trending startup funding round, acquisition, or founder story. "
             "Focus on the human drama or contrarian business lesson, not just the numbers."),

            ("How-To & Productivity",
             "Identify a practical tool, workflow hack, or productivity technique that is "
             "going viral among developers, designers, or knowledge workers right now."),

            ("Tech Industry Drama",
             "Find a current controversy, lawsuit, rivalry, or public spat in the tech world "
             "(e.g. company vs regulator, CEO vs employees, open-source vs closed-source debate). "
             "Readers love insider drama."),

            ("Gadgets & Consumer Tech",
             "Pick a newly launched or leaked consumer gadget, app, or platform feature "
             "that people are excited or outraged about this week."),

            ("Career & Future of Work",
             "Find a trending topic about jobs, salaries, remote work, layoffs, or skills "
             "in the tech industry. Frame it around what readers should *do* about it."),

            ("Science Meets Tech",
             "Pick a story where cutting-edge science intersects with technology — "
             "biotech, space, climate tech, quantum computing breakthroughs, etc."),
        ]

        genre_label, genre_instruction = random.choice(GENRE_WHEEL)
        print(f"\n🎯 Selected content genre: [{genre_label}]")

        trend_researcher = Agent(
            role="Trend Research Analyst",
            goal=(
                f"Find one highly engaging, shareable trending topic in the genre: '{genre_label}'. "
                "The topic must be fresh (last 7 days), specific, and have a clear reader hook."
            ),
            backstory=(
                "You scan Reddit, Hacker News, TechCrunch, The Verge, Twitter/X trending, "
                "and news aggregators daily. You have a journalist's nose for what will make "
                "people click, share, and argue in the comments. "
                "You avoid vague evergreen topics — you always anchor to a current event or "
                "a real, specific thing happening RIGHT NOW. "
                "Sources must be authentic: news sites, Reddit threads, official announcements."
            ),
            allow_delegation=False,
            verbose=True,
            tools=[trend_keyword_tool],
            llm=self.my_llm
        )

        discover_trend = Task(
            description=(
                f"Content genre for today: **{genre_label}**\n\n"
                f"Your mission: {genre_instruction}\n\n"
                "Steps:\n"
                "1. Use your search tools to find what is trending RIGHT NOW in this genre.\n"
                "2. Choose ONE specific topic — not a broad category. "
                "   Good: 'OpenAI fires safety team lead amid board drama' "
                "   Bad: 'AI safety is important'\n"
                "3. Confirm the topic has real search interest and fresh news hooks.\n"
                "4. Write a 2-sentence brief: what the topic is + why readers will care today."
            ),
            expected_output=(
                f"Genre: {genre_label}\n"
                "Topic: [one specific, concrete trending topic]\n"
                "Why now: [2 sentences explaining recency and reader appeal]\n"
                "Suggested angle: [one punchy article framing — e.g. 'The insider story of...', "
                "'5 things nobody is saying about...', 'Why X just changed everything about Y']"
            ),
            agent=trend_researcher,
        )

        return trend_researcher, discover_trend
    
    def planner_agent(self):
        planner = Agent(
            role="Content Planner",
            goal="Create an engaging and data-backed content plan for a trending topic.",
            backstory=(
                "You work with the Trend Research Analyst who identifies trending topics. "
                "Based on the chosen topic, you outline the article structure, "
                "target audience, key subtopics, and SEO keywords for maximum reach."
            ),
            allow_delegation=False,
            verbose=True,
            tools=[serper_fetch_tool],
            llm=self.my_llm
        )

        plan = Task(
                description=(
                    "1. Take the trending topic identified by the Trend Research Analyst.\n"
                    "2. Use the search tool to fetch top related articles and data.\n"
                    "3. Build a detailed blog outline, target audience, SEO plan, and reference list."
                ),
                expected_output=(
                    "A detailed content plan including:\n"
                    "- Blog structure (intro, sections, CTA)\n"
                    "- SEO keywords\n"
                    "- Target audience\n"
                    "- Reference sources"
                ),
                agent=planner,
            )

        return planner,plan
    
    def write_agent(self):

        STYLE_PROMPT = """
        You are an SEO-optimized blog writer who creates WordPress-ready HTML articles
        that score 100/100 on RankMath or Yoast SEO.

        Your article will be scored by RankMath. To reach 100/100 you must ensure:

        1️⃣ Focus Keyword
        - Appears in: SEO title, meta description, URL slug, first paragraph, at least one sub-heading (H2–H4).
        - combined density ~1.0–1.5%.
        - Keyword or variation must appear at least 5 times in 1 000 words.

        2️⃣ Title
        - Under 60 characters, includes focus keyword + power word + number (e.g., “7 Ways”, “Ultimate”, “Proven”).
        - Starts with focus keyword.This title should contain aleast one of the following power words: Amazing, Ultimate, Best, Complete, Proven, Guide and at least one number like Top 10, 5 Ways, 3 Secrets etc.,

        3️⃣ Meta Description
        - Under 160 characters and naturally contains focus keyword.

        4️⃣ URL
        - Slug includes focus keyword, all lowercase, hyphen-separated.

        5️⃣ Content Body
        - Begin first sentence with focus keyword.
        - Use short paragraphs (< 120 words each).
        - Include transition words and active voice.
        - INTERNAL LINKS: Call get_all_internal_links tool first. Use ONLY exact URLs it returns. 10-12 internal links.
        - EXTERNAL LINKS: Write 3-5 external links using DESCRIPTIVE ANCHOR TEXT only. Set href="SERPER_RESOLVE" as a placeholder — the pipeline will automatically replace it with a real verified URL from Google. Example: <a href="SERPER_RESOLVE" target="_blank" rel="noopener">how AI is changing outsourcing in India</a>. Do NOT invent URLs. Do NOT use example.com. Just write good anchor text.
        - DO NOT include any <img> tags in the content. The cover image will be added separately as featured image.

        6️⃣ Headings
        - Use one <h1>, multiple <h2>/<h3>; at least one contains focus keyword.

        7️⃣ Extras
        - title should contain atleast one number & one power word.
        - Conclude with CTA paragraph.
        - JSON-LD article schema at bottom.

        No Markdown, no explanations — H
        TML only.
        No Footer Part Its already There in Wordpress Website Just Focus On getting SEO 100 SCRORE
        When generating, explicitly verify each rule before output.
        """


        writer = Agent(
            role="Content Writer",
            goal="Write a perfect 100/100 SEO article in valid HTML format for WordPress.",
            backstory="You are an SEO expert writer who ensures every article passes RankMath with full score.",
            instructions=STYLE_PROMPT,
            allow_delegation=False,
            verbose=True,
            llm=self.my_llm,
            tools=[get_all_internal_links]
        )

        write = Task(
                description=(
                    "1. Write a complete SEO-optimized blog article using HTML only (no Markdown).\n"
                    "2. Follow a WordPress-friendly structure with meta tags, headings, and internal/external links.\n"
                    "3. Include 3–5 <h2> sections, relevant <h3> subsections. DO NOT include any <img> tags - the featured image will be added separately."
                    "4. Ensure the article includes a meta title (<60 chars), meta description (<160 chars), and is engaging and factual.\n"
                    "5. Output only the full HTML document (<!DOCTYPE html> ... </html>) with no Markdown or commentary.\n"
                    "6. Use atleast 1 number & 1 power word in the title."
                    "7. May you give this at the end article make it suitable place.Internal should be 10-12 links and external should be 3-5 links."
                 
                ),
                expected_output="A full WordPress-ready SEO article in valid HTML format only.",
                agent=writer,
            )
        return writer,write

    def editor_agent(self):

        editor = Agent(
            role="Editor",
            goal="Refine and finalize the written article for publication.",
            backstory=(
                "You receive a blog draft from the Writer and ensure it follows Medium's tone, "
                "is error-free, balanced, and ready for public release.Ensure the article is engaging, and check does it contain internal links refer get all internal links tool.If not then add atleast one internal link and one external link with rel='noopener' and target='_blank'."
            ),
            allow_delegation=False,
            verbose=True,
            tools=[get_all_internal_links],
            llm=self.my_llm
        )

        edit = Task(
            description=(
                """1. Review and refine the written article.\n"""
                "2. Fix grammar, tone, and flow.\n"
                "3. Ensure it's ready for Medium publication."
                "4. Check for internal and external links; add if missing."
                "5. Overall content lenths should be between 1500 to 2000 words."
                "6. CRITICAL: External links must be REAL, EXISTING articles from trusted sources (Reuters, CNBC, Wired, TechCrunch, ArsTechnica, The Verge, BBC, NYTimes, etc.). DO NOT use placeholder URLs. Verify each external link points to a real article."
                "7. Include 10-12 internal links from """+WP_URL+""" and 3-5 REAL external links to high-authority sources."
                "8. Double-check that ALL external links are valid, working URLs to actual articles - NO placeholders, NO hypothetical links."""
                
            ),
            expected_output="Final polished article ready for publication.",
            agent=editor,
        )
        return editor,edit
    
    def designer_agent(self):   
        designer = Agent(
            role="Banner Designer",
            goal="Find and select a visually appealing, relevant banner image for the article.",
            backstory=(
                "You are a skilled digital designer. "
                "You search the web for modern, relevant, and aesthetic images that match the blog topic."
            ),
            allow_delegation=False,
            verbose=True,
            tools=[image_search_tool],
            llm=self.my_llm
        )

        design_banner = Task(
                description="Search and download a banner image related to the blog topic.",
                expected_output="A path to the downloaded banner image.",
                agent=designer)
        return designer,design_banner



    def seo_expert_agent(self):

        seo_expert_agent = Agent(
            role="SEO Expert & Content Optimizer",
            goal=(
                "Analyze and optimize the final HTML article to achieve a perfect SEO score (100/100) "
                "based on the specified SEO checklist."
            ),
            backstory=(
                "You are an experienced SEO specialist with expertise in on-page optimization for WordPress blogs. "
                "Your job is to review and enhance an HTML article to meet every SEO best practice — including keyword "
                "placement, meta optimization, link strategy, readability, and structure."
            ),
            instructions=(
                """You will receive a full HTML article and the Focus Keyword.\n"
                "Your task is to verify and if necessary, modify the HTML to ensure all the following requirements are met:\n\n"
                "✅ Title :\n"
                "- Under 60 characters.\n"
                "- Includes Focus Keyword near the start.\n"
                "- Contains at least one power word (e.g., 'Amazing', 'Ultimate', 'Best', 'Complete', 'Proven', 'Guide').\n"
                "- Contains at least one number (e.g., 'Top 10', '5 Ways', '3 Secrets').\n\n"
                "✅ Focus Keyword (3-4 keywords, comma-separated):\n"
                "- Primary keyword (first) MUST appear in: SEO Title (<title>) at the beginning, Meta Description, URL slug, first 100 words.\n"
                "- All 3-4 keywords should be distributed across: title, meta description, H2/H3 headings, and content body.\n"
                "- Do NOT generate <img> tags - the featured image is handled separately.\n\n"
                "✅ Content Optimization:\n"
                "- Word count between 1500 and 2000.\n"
                "- Keyword density for all 3-4 keywords combined should be around 1% (not zero, not excessive).\n"
                "- Add or modify text if needed to adjust density naturally.\n"
                "- Include a Table of Contents (with <nav> or <ul>) after the introduction.\n"
                "- Use short, readable paragraphs (<p>) under 120 words.\n"
                "- DO NOT add any <img> tags to the article body.\n\n"
                "✅ Links:\n"
                "- Include at least one internal link (href='/blog/...').\n"
                "- Include at least one external link (href='https://...') with rel='noopener' and target='_blank'.\n\n"
                "- Internal should be 10-12 links and external should be 3-5 links\n"
                "- CRITICAL: External links MUST be REAL, EXISTING articles from trusted sources (Reuters, CNBC, Wired, TechCrunch, ArsTechnica, The Verge, BBC, NYTimes, etc.). DO NOT use placeholder URLs like 'medium.com/@yourprofile'. Verify each link exists.\n\n"
                "✅ SEO Title Formatting:\n"
                "- Title length under 60 characters.\n"
                "- Include the Focus Keyword near the start.\n"
                "- Include at least one power word (like 'Amazing', 'Ultimate', 'Best', 'Complete', 'Proven', 'Guide').\n"
                "- Include at least one number (like 'Top 10', '5 Ways', '3 Secrets', etc.).\n\n"
                "✅ Technical SEO:\n"
                "- Add <meta name='description'> under 160 characters.\n"
                "- Use a clean slug under 30 characters in the canonical or meta URL.\n"
                "- Ensure at least one image or video is embedded.\n"
                "- Add a Table of Contents (<nav> or <ul> linked to #ids in headings).\n\n"
                "If any requirement is missing, modify the HTML structure and re-output the fully optimized version.\n\n"
                "❌ Do not add Markdown or commentary. Only return a complete, clean HTML document (<html>...</html>)."

                "**Mind it we fetch focus keyword from final generated article by you so the focus keyword should be in beggining of the article and also in title,meta description,alt text,headings etc.That foucus keyword should have one 1 percentage density of overall artcile **"
                "**Also Make Sure are you using sub headings h2 and h3 in article .Also make sure that article length should be between 1500 to 2000 words .**"
                "**Dont forgot use get_all_internal_links tool to fetch internal links from """+WP_URL+""" and use atleast 10-12 internal links and 3-5 external links in article.**"""
            ),
            allow_delegation=False,
            tools=[get_all_internal_links],
            verbose=True,
            llm=self.my_llm
        )

        seo_expert = Task(
            description=(
                "Review and enhance the Writer Agent's HTML article for full SEO optimization. "
                "Check all criteria — keyword usage, title, meta description, internal/external links, "
                "image alt text, table of contents, readability, and word count (1500–2000). "
                "If any are missing or suboptimal, edit the HTML to achieve a perfect SEO score (100/100)."
            ),
            expected_output="A fully SEO-optimized HTML article (no Markdown) ready for WordPress publishing.",
            agent=seo_expert_agent,
        )
        return seo_expert_agent,seo_expert

    def generate_article(self):
        trend_researcher,discover_trend = self.trend_resarcher_agent()
        planner,plan = self.planner_agent()
        writer,write = self.write_agent()
        editor,edit = self.editor_agent()
        designer,design_banner = self.designer_agent()
        seo_expert_agent,seo_expert = self.seo_expert_agent()
        crew = Crew(
            agents=[trend_researcher, planner, editor, designer,writer,seo_expert_agent],
            tasks= [discover_trend, plan, write,edit, design_banner, seo_expert],
            verbose=True,
        )

        # Kickoff — full automatic pipeline
        result = crew.kickoff()
        # print(result)

        html_output = result.raw

        local_image_path = None
        for task in crew.tasks:
            # Find the output from the designer agent's task
            if task.agent.role == "Banner Designer":
                local_image_path = task.output.raw.strip() 
                # Handle cases where the tool failed
                if local_image_path.startswith("❌") or local_image_path.startswith("⚠️"):
                    print(f"Designer task failed or found no image: {local_image_path}")
                    local_image_path = None
                break

        # Clean markdown-style code fences if present
        if html_output.startswith("```html"):
            html_output = html_output.replace("```html", "").replace("```", "").strip()

        return html_output,local_image_path