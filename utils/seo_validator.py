"""
SEO Validator Module
Validates articles meet SEO requirements before publishing.
"""
import re
from bs4 import BeautifulSoup
from collections import Counter


# Power words that increase click-through rates
POWER_WORDS = [
    'amazing', 'ultimate', 'best', 'complete', 'proven', 'guide', 
    'essential', 'powerful', 'incredible', 'exclusive', 'secret',
    'revolutionary', 'guaranteed', 'expert', 'professional', 'simple',
    'easy', 'quick', 'fast', 'instant', 'free', 'new', 'top',
    'must-have', 'critical', 'vital', 'important', 'effective',
    'comprehensive', 'definitive', 'master', 'brilliant', 'stunning'
]


def calculate_keyword_density(html_content: str, focus_keyword: str) -> float:
    """
    Calculates combined keyword density for 3-4 comma-separated keywords.
    Target: ~1.0% combined density is optimal for SEO.
    
    Args:
        html_content: HTML content to analyze
        focus_keyword: Comma-separated keywords (e.g., "ai technology, machine learning, artificial intelligence")
    
    Returns:
        Combined keyword density as percentage
    """
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text().lower()
    
    # Remove extra whitespace
    words = text.split()
    total_words = len(words)
    
    if total_words == 0:
        return 0.0
    
    # Parse comma-separated keywords
    keywords = [kw.strip().lower() for kw in focus_keyword.split(',') if kw.strip()]
    
    if not keywords:
        return 0.0
    
    # Count total occurrences of all keywords combined
    total_keyword_words = 0
    for keyword in keywords:
        keyword_count = text.count(keyword)
        keyword_word_count = len(keyword.split())
        total_keyword_words += keyword_count * keyword_word_count
    
    # Calculate combined density
    density = (total_keyword_words / total_words) * 100
    
    return round(density, 2)


def check_keyword_in_first_100_words(html_content: str, focus_keyword: str) -> bool:
    """
    Checks if PRIMARY (first) keyword from comma-separated list appears in the first 100 words.
    
    Args:
        html_content: HTML content to analyze
        focus_keyword: Comma-separated keywords (e.g., "ai technology, machine learning")
    
    Returns:
        True if primary keyword found in first 100 words
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Get text content
    body = soup.find("body")
    if body:
        text = body.get_text()
    else:
        text = soup.get_text()
    
    # Get first 100 words
    words = text.split()[:100]
    first_100_text = " ".join(words).lower()
    
    # Extract primary (first) keyword from comma-separated list
    primary_keyword = focus_keyword.split(',')[0].strip().lower()
    
    return primary_keyword in first_100_text


def check_power_words_in_title(title: str) -> tuple:
    """
    Checks if title contains power words.
    Returns (has_power_word, list_of_found_power_words)
    """
    title_lower = title.lower()
    found_words = [word for word in POWER_WORDS if word in title_lower]
    return (len(found_words) > 0, found_words)


def check_number_in_title(title: str) -> bool:
    """
    Checks if title contains a number (e.g., "5 Ways", "Top 10").
    """
    return bool(re.search(r'\d+', title))


def count_internal_links(html_content: str, site_domain: str = "readtechflow.com") -> int:
    """
    Counts internal links in the content.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    links = soup.find_all("a", href=True)
    
    internal_count = 0
    for link in links:
        href = link["href"].lower()
        if site_domain in href or href.startswith("/"):
            internal_count += 1
    
    return internal_count


def count_external_links(html_content: str, site_domain: str = "readtechflow.com") -> int:
    """
    Counts external links in the content.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    links = soup.find_all("a", href=True)
    
    external_count = 0
    for link in links:
        href = link["href"].lower()
        if href.startswith("http") and site_domain not in href:
            external_count += 1
    
    return external_count


def check_paragraph_lengths(html_content: str, max_words: int = 120) -> tuple:
    """
    Checks if any paragraphs exceed the maximum word count.
    Returns (all_pass, list_of_long_paragraphs_word_counts)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    paragraphs = soup.find_all("p")
    
    long_paragraphs = []
    for p in paragraphs:
        word_count = len(p.get_text().split())
        if word_count > max_words:
            long_paragraphs.append(word_count)
    
    return (len(long_paragraphs) == 0, long_paragraphs)


def validate_seo(html_content: str, focus_keyword: str, seo_title: str, url_slug: str) -> dict:
    """
    Comprehensive SEO validation.
    Returns dict with scores and issues.
    """
    issues = []
    score = 100
    
    # 1. Keyword Density (target ~1.0% combined for 3-4 keywords)
    density = calculate_keyword_density(html_content, focus_keyword)
    if density < 0.5:
        issues.append(f"❌ Keyword density too low: {density}% (target: ~1.0%)")
        score -= 15
    elif density > 2.5:
        issues.append(f"⚠️ Keyword density too high: {density}% (target: ~1.0%, may be seen as spam)")
        score -= 10
    elif density < 0.8 or density > 1.5:
        issues.append(f"⚠️ Keyword density slightly off target: {density}% (ideal: 0.8-1.5%)")
        score -= 5
    else:
        print(f"✅ Keyword density: {density}%")
    
    # 2. Keyword in first 100 words
    if not check_keyword_in_first_100_words(html_content, focus_keyword):
        issues.append("❌ Focus keyword not in first 100 words")
        score -= 10
    else:
        print("✅ Focus keyword found in first 100 words")
    
    # 3. Power words in title
    has_power, found_power = check_power_words_in_title(seo_title)
    if not has_power:
        issues.append("❌ No power words in title")
        score -= 10
    else:
        print(f"✅ Power words in title: {found_power}")
    
    # 4. Number in title
    if not check_number_in_title(seo_title):
        issues.append("⚠️ No number in title (e.g., '5 Ways', 'Top 10')")
        score -= 5
    else:
        print("✅ Number found in title")
    
    # 5. URL slug length
    if len(url_slug) > 65:
        issues.append(f"❌ URL slug too long: {len(url_slug)} chars (max: 65)")
        score -= 10
    else:
        print(f"✅ URL slug length: {len(url_slug)} chars")
    
    # 6. Internal links (target 10-12)
    internal_count = count_internal_links(html_content)
    if internal_count < 5:
        issues.append(f"❌ Too few internal links: {internal_count} (target: 10-12)")
        score -= 15
    elif internal_count < 10:
        issues.append(f"⚠️ Low internal links: {internal_count} (target: 10-12)")
        score -= 5
    else:
        print(f"✅ Internal links: {internal_count}")
    
    # 7. External links (target 3-5)
    external_count = count_external_links(html_content)
    if external_count < 2:
        issues.append(f"❌ Too few external links: {external_count} (target: 3-5)")
        score -= 10
    elif external_count < 3:
        issues.append(f"⚠️ Low external links: {external_count} (target: 3-5)")
        score -= 5
    else:
        print(f"✅ External links: {external_count}")
    
    # 8. Paragraph lengths
    para_ok, long_paras = check_paragraph_lengths(html_content)
    if not para_ok:
        issues.append(f"⚠️ {len(long_paras)} paragraphs exceed 120 words")
        score -= 5
    else:
        print("✅ All paragraphs under 120 words")
    
    # Calculate pass/fail
    passed = score >= 80
    
    result = {
        "score": max(0, score),
        "passed": passed,
        "issues": issues,
        "details": {
            "keyword_density": density,
            "internal_links": internal_count,
            "external_links": external_count,
            "url_slug_length": len(url_slug)
        }
    }
    
    print(f"\n{'✅' if passed else '❌'} SEO Score: {result['score']}/100 {'(PASSED)' if passed else '(FAILED)'}")
    
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  {issue}")
    
    return result
