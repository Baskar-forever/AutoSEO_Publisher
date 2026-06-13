"""
Table of Contents Generator
Generates TOC from article headings.
"""
from bs4 import BeautifulSoup
import re


def generate_toc(html_content: str) -> str:
    """
    Generates a Table of Contents HTML from H2 and H3 headings.
    Returns TOC HTML to be inserted into the article.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Find all H2 and H3 headings
    headings = soup.find_all(['h2', 'h3'])
    
    if len(headings) < 3:
        # Too few headings for a meaningful TOC
        return ""
    
    toc_items = []
    
    for i, heading in enumerate(headings):
        text = heading.get_text().strip()
        
        # Skip FAQ heading
        if "faq" in text.lower() or "frequently asked" in text.lower():
            continue
        
        # Generate ID for the heading (if not exists)
        heading_id = heading.get('id')
        if not heading_id:
            heading_id = slugify_heading(text)
            heading['id'] = heading_id
        
        level = heading.name  # 'h2' or 'h3'
        indent_class = "toc-h3" if level == 'h3' else "toc-h2"
        
        toc_items.append({
            'text': text,
            'id': heading_id,
            'level': level,
            'class': indent_class
        })
    
    if not toc_items:
        return ""
    
    # Build TOC HTML
    toc_html = '''
<nav class="table-of-contents" style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
    <h2 style="margin-top: 0; font-size: 1.25rem;">Table of Contents</h2>
    <ul style="list-style: none; padding-left: 0; margin-bottom: 0;">
'''
    
    for item in toc_items:
        padding = "padding-left: 20px;" if item['level'] == 'h3' else ""
        toc_html += f'''        <li style="margin: 8px 0; {padding}">
            <a href="#{item['id']}" style="color: #0066cc; text-decoration: none;">{item['text']}</a>
        </li>
'''
    
    toc_html += '''    </ul>
</nav>
'''
    
    return toc_html


def slugify_heading(text: str) -> str:
    """Convert heading text to URL-friendly ID."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text[:50] or 'section'


def inject_toc(html_content: str) -> str:
    """
    Injects Table of Contents after the first paragraph or intro section.
    Also adds IDs to headings if missing.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Generate TOC and update heading IDs
    toc_html = generate_toc(html_content)
    
    if not toc_html:
        return html_content
    
    # Re-parse to get updated heading IDs
    headings = soup.find_all(['h2', 'h3'])
    for heading in headings:
        text = heading.get_text().strip()
        if not heading.get('id'):
            heading['id'] = slugify_heading(text)
    
    # Find insertion point (after first paragraph or at start of body)
    body = soup.find('body')
    if body:
        first_p = body.find('p')
        if first_p:
            # Insert after first paragraph
            toc_soup = BeautifulSoup(toc_html, 'html.parser')
            first_p.insert_after(toc_soup)
        else:
            # Insert at beginning of body
            toc_soup = BeautifulSoup(toc_html, 'html.parser')
            body.insert(0, toc_soup)
    
    print("✅ Table of Contents added")
    return str(soup)
