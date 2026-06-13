# 🤖 AutoSEO_Publisher

An enterprise-grade, zero-touch content generation pipeline powered by **CrewAI**. This system doesn't just write articles; it researches trends, generates media, injects JSON-LD schemas, audits links, and uses an **Agentic Self-Healing Loop** to guarantee an 80+ RankMath SEO score before autonomously deploying to WordPress via GitHub Actions.

## ✨ Key Features

* **Multi-Agent Swarm (CrewAI):** Utilizes specialized agents (Trend Researcher, Planner, Writer, Editor, Designer, and SEO Expert) to handle the entire editorial pipeline.
* **Agentic SEO Reflection Loop:** The system scores its own generated HTML against strict RankMath SEO criteria (keyword density, slug length, title power words). If the score falls below 80/100, the pipeline halts and hands the HTML back to the LLM to autonomously rewrite and fix the issues.
* **Media Optimization:** Automatically fetches relevant banner images, resizes them, and converts them to highly compressed `WebP` formats for optimal Core Web Vitals.
* **Deterministic Middleware:** Uses Python (BeautifulSoup) to physically ping and audit generated URLs, inject `<nav>` Table of Contents, and append FAQ Schema markup (`application/ld+json`).
* **CI/CD Automation:** Fully decoupled and Docker/Ubuntu ready. Runs entirely hands-free on a 3-day cron schedule via GitHub Actions.

## 🏗️ System Architecture

1. **Trend Discovery:** Scrapes Google Search (via Serper) for trending tech/AI topics.
2. **Draft Generation:** Agents outline, write, and format a 1,500+ word HTML article.
3. **Middleware Processing:** - Downloads and optimizes images.
   - Injects dynamic TOC and FAQ schema.
   - Audits external links to ensure they point to real, authoritative domains.
4. **Validation Loop:** Validates SEO. If failed, it triggers a rewrite loop up to 2 times.
5. **Deployment:** Pushes the finalized HTML, metadata, and featured image to the WordPress REST API.

## ⚙️ Quick Start Setup

### 1. Prerequisites
* Python 3.10+
* A WordPress website with Application Passwords enabled.
* API Keys for your LLM (OpenAI/Gemini) and Serper.dev.

### 2. Installation
Clone the repository and install the dependencies:
```bash
git clone [https://github.com/Baskar-forever/AutoSEO_Publisher](https://github.com/Baskar-forever/AutoSEO_Publisher)
cd AutoSEO_Publisher
pip install -r requirements.txt
3. Environment Variables
Create a .env file in the root directory (refer to .env.example):

Code snippet
# LLM Configuration
OPENAI_API_KEY="your_api_key_here"
MODEL="gemini/gemini-2.5-flash" # Or "gpt-4o"

# Search Tools
SERPER_API_KEY="your_serper_api_key_here"

# WordPress Configuration
WP_URL="[https://yourwebsite.com](https://yourwebsite.com)"
WP_USER="your_wp_username"
WP_APP_PASSWORD="your_wp_application_password_here"
🚀 Usage
Run Locally:
To test the pipeline on your local machine and publish a live post:

Bash
python main.py --index
(Note: Use --noindex to push a draft that blocks Google bots while you test).

Run via CI/CD (GitHub Actions):
The repository includes a .github/workflows/auto_publish.yml file.

Go to your GitHub Repository Settings > Secrets and Variables > Actions.

Add your .env variables as Repository Secrets.

The pipeline will automatically wake up and publish a new article every 3 days.

🛡️ License
Distributed under the MIT License. See LICENSE for more information.