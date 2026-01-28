#!/usr/bin/env python3
"""
URL to Markdown Scraper (url2md)
==================================

Converts web pages to markdown files from their URLs, with support for multi-URL processing,
path-based crawling, and sitemap.xml parsing.

Features:
- Single or multi-URL scraping
- Path-based crawling (e.g., /blog/ → all blog articles)
- sitemap.xml support with filtering
- Preserved folder structure
- Intelligent HTML cleaning
- Optimized for French content

Author: phenates
"""

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


# ============================================================
# STRING & PATH UTILITIES
# ============================================================
def sanitize_filename(title):
    """
    Converts a title to a valid filename.

    Args:
        title (str): Page title to sanitize

    Returns:
        str: Sanitized filename (lowercase, dashed, max 100 chars)

    Examples:
        >>> sanitize_filename("Hello World!")
        'hello-world'
        >>> sanitize_filename("Article: Python Tips & Tricks")
        'article-python-tips-tricks'
    """
    # Remove special characters
    title = re.sub(r'[^\w\s-]', '', title)
    # Replace spaces with dashes
    title = re.sub(r'[\s_:]+', '-', title)
    # Convert to lowercase
    title = title.lower().strip('-')
    # Limit length
    return title[:100] if title else 'untitled'


def get_output_path(url, title, output_dir):
    """
    Generates output path while preserving URL structure.

    Args:
        url (str): Source URL
        title (str): Page title (for filename)
        output_dir (str): Root output directory

    Returns:
        Path: Full path of file to create

    Example:
        url = "https://example.com/blog/2024/article"
        → output_dir/example.com/blog/2024/article.md
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path.strip('/')

    # Early return for empty path
    if not path:
        filename = sanitize_filename(
            title if title != 'untitled' else 'index') + '.md'
        return Path(output_dir) / domain / filename

    # Extract folders and base name
    path_parts = path.split('/')
    dir_parts = path_parts[:-1]
    file_base = path_parts[-1] or 'index'

    # Build the path
    base_path = Path(output_dir) / domain
    if dir_parts:
        base_path = base_path / Path(*dir_parts)

    filename = sanitize_filename(
        title if title != 'untitled' else file_base) + '.md'
    return base_path / filename


# ============================================================
# HTML PROCESSING
# ============================================================
def extract_title(soup):
    """
    Extracts page title using multiple fallback methods.

    Tries in order:
    1. <title> tag
    2. og:title meta tag
    3. First <h1> element
    4. Fallback to "untitled"

    Args:
        soup (BeautifulSoup): Parsed HTML document

    Returns:
        str: Extracted title or "untitled"
    """
    # 1. <title> tag
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    # 2. Meta og:title
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()

    # 3. First <h1>
    h1 = soup.find('h1')
    if h1:
        return h1.get_text().strip()

    # 4. Fallback to URL
    return "untitled"


def convert_relative_to_absolute_urls(soup, base_url):
    """
    Converts all relative URLs to absolute URLs.

    Processes:
    - href attributes in <a> tags
    - src attributes in <img> tags
    - srcset attributes for responsive images

    Args:
        soup (BeautifulSoup): Parsed HTML document
        base_url (str): Base URL for resolving relative links

    Returns:
        BeautifulSoup: Modified soup object with absolute URLs
    """
    # Convert href links (<a> tags)
    for link in soup.find_all('a', href=True):
        link['href'] = urljoin(base_url, link['href'])

    # Convert image src (<img> tags)
    for img in soup.find_all('img', src=True):
        img['src'] = urljoin(base_url, img['src'])

    # Convert srcset sources (responsive images)
    for img in soup.find_all('img', srcset=True):
        srcset_parts = []
        for part in img['srcset'].split(','):
            part = part.strip()
            if ' ' in part:
                url, descriptor = part.rsplit(' ', 1)
                url = urljoin(base_url, url.strip())
                srcset_parts.append(f"{url} {descriptor}")
            else:
                srcset_parts.append(urljoin(base_url, part))
        img['srcset'] = ', '.join(srcset_parts)

    return soup


def clean_html(soup):
    """
    Cleans HTML before conversion by removing navigation and clutter elements.

    Removes:
    - Navigation elements (nav, header, footer)
    - Scripts and styles
    - Forms, iframes, buttons
    - Common navigation classes (navbar, sidebar, menu, etc.)
    - Advertisement and social sharing widgets
    - Skip-to-content links

    Preserves:
    - <aside> elements with content classes (callouts, notes, tips)
    - <details>/<summary> elements (tabs, collapsible sections)

    Args:
        soup (BeautifulSoup): Parsed HTML document

    Returns:
        BeautifulSoup: Cleaned soup object
    """
    # Elements to remove by tag name (NOTE: 'aside' removed from this list)
    unwanted_tags = ['nav', 'header', 'footer', 'script', 'style',
                     'iframe', 'noscript', 'button', 'form']

    for tag in unwanted_tags:
        for element in soup.find_all(tag):
            element.decompose()

    # Selectively remove <aside> elements (only navigation/sidebar ones, not content)
    for aside in soup.find_all('aside'):
        classes = ' '.join(aside.get('class', [])).lower()
        # Preserve asides with content-related classes (callouts, notes, tips, warnings)
        content_keywords = ['callout', 'note', 'tip', 'warning', 'info', 'caution',
                            'starlight-aside', 'admonition', 'alert']
        if not any(keyword in classes for keyword in content_keywords):
            # Remove navigation/sidebar asides
            if any(word in classes for word in ['sidebar', 'navigation', 'nav', 'menu']):
                aside.decompose()

    # Unwrap unnecessary <details> wrappers but preserve content
    # (markdownify will handle the remaining structure)
    for details in soup.find_all('details'):
        classes = ' '.join(details.get('class', [])).lower()
        # For tab containers, extract content from all tabs
        if 'tab' in classes:
            # Find all tab panels within this details element
            tab_panels = details.find_all(
                class_=re.compile(r'tab.*panel', re.I))
            if tab_panels:
                # Create a wrapper div for all tab content
                wrapper = soup.new_tag('div')
                wrapper['class'] = 'tabs-content'

                for panel in tab_panels:
                    # Extract tab title if available
                    tab_label = panel.get('aria-labelledby', '')
                    if tab_label:
                        # Find the corresponding label
                        label_elem = soup.find(id=tab_label)
                        if label_elem:
                            title = soup.new_tag('h4')
                            title.string = label_elem.get_text().strip()
                            wrapper.append(title)

                    # Add panel content
                    wrapper.append(panel)

                # Replace details with wrapper
                details.replace_with(wrapper)

    # Classes/IDs often related to navigation
    unwanted_classes = ['navigation', 'navbar', 'sidebar', 'menu', 'footer',
                        'header', 'breadcrumb', 'social', 'share', 'cookie',
                        'advertisement', 'ad-', 'banner', 'popup', 'skip',
                        'category', 'tag-list', 'meta-', 'badge']

    for class_name in unwanted_classes:
        for element in soup.find_all(class_=re.compile(class_name, re.I)):
            element.decompose()

    # Remove "skip to content" links
    for link in soup.find_all('a', href=re.compile(r'#.*top|#content|#main', re.I)):
        link.decompose()

    return soup


def convert_callouts_to_markdown(soup):
    """
    Converts HTML callout/admonition blocks to Markdown callout format.

    Detects common callout patterns in HTML (divs/aside with classes like
    note, warning, tip, caution, important) and converts them to Obsidian/GitHub
    callout format: > [!TYPE]

    Supported callout types:
    - NOTE, INFO, HINT
    - TIP, SUCCESS
    - WARNING, CAUTION, ATTENTION
    - DANGER, ERROR, CRITICAL
    - EXAMPLE
    - QUESTION, FAQ
    - QUOTE, CITE

    Args:
        soup (BeautifulSoup): Parsed HTML document

    Returns:
        BeautifulSoup: Modified soup with callouts converted to blockquotes

    Example:
        HTML: <div class="note">This is important</div>
        Result: <blockquote data-callout="NOTE">This is important</blockquote>
    """
    # Mapping of CSS class patterns to callout types
    callout_mappings = {
        'note': 'NOTE',
        'info': 'NOTE',
        'hint': 'NOTE',
        'tip': 'TIP',
        'success': 'TIP',
        'important': 'IMPORTANT',
        'warning': 'WARNING',
        'caution': 'WARNING',
        'attention': 'WARNING',
        'danger': 'DANGER',
        'error': 'DANGER',
        'critical': 'DANGER',
        'example': 'EXAMPLE',
        'question': 'QUESTION',
        'faq': 'QUESTION',
        'quote': 'QUOTE',
        'cite': 'QUOTE',
        'admonition': 'NOTE',
    }

    # Tags that typically contain callouts
    callout_tags = ['div', 'aside', 'blockquote', 'section']

    for tag_name in callout_tags:
        for element in soup.find_all(tag_name):
            # Skip if this element is already inside another callout/blockquote
            # Check if any parent already has callout classes or is a blockquote
            parent_is_callout = False
            for parent in element.parents:
                if parent.name == 'blockquote':
                    parent_is_callout = True
                    break
                parent_classes = parent.get('class', [])
                if parent_classes:
                    parent_classes_str = ' '.join(parent_classes).lower()
                    for pattern in callout_mappings.keys():
                        if pattern in parent_classes_str:
                            parent_is_callout = True
                            break
                if parent_is_callout:
                    break

            if parent_is_callout:
                continue

            # Get all classes as lowercase
            classes = element.get('class', [])
            if not classes:
                continue

            classes_str = ' '.join(classes).lower()

            # Check if any callout pattern matches
            callout_type = None
            for pattern, ctype in callout_mappings.items():
                if pattern in classes_str:
                    callout_type = ctype
                    break

            if callout_type:
                # Extract title if present (often in a nested element)
                title = None
                title_elem = element.find(['p', 'div', 'span'], class_=re.compile(r'title|heading|header', re.I))
                if title_elem:
                    title = title_elem.get_text().strip()
                    title_elem.decompose()  # Remove title element

                # Create new blockquote with a special marker
                blockquote = soup.new_tag('blockquote')

                # Add callout marker that will survive markdown conversion
                marker = soup.new_tag('p')
                if title:
                    marker.string = f'[!{callout_type}] {title}'
                else:
                    marker.string = f'[!{callout_type}]'
                blockquote.append(marker)

                # Move all content to blockquote
                for child in list(element.children):
                    blockquote.append(child)

                # Replace original element
                element.replace_with(blockquote)

    return soup


# ============================================================
# MARKDOWN CLEANUP
# ============================================================
def fix_broken_words(markdown_text):
    """
    Repairs words broken mid-line by newlines.

    Handles cases where HTML rendering split words across lines:
    - "effi\\ncace" → "efficace"
    - "Dockerfi\\nle" → "Dockerfile"

    Uses two patterns:
    1. Letters + newline + lowercase letters (general case)
    2. Letter + newline before lowercase (within sentences)

    Args:
        markdown_text (str): Markdown content with potential broken words

    Returns:
        str: Text with repaired words
    """
    # Pattern 1: letters + \n + letters (general case)
    markdown_text = re.sub(
        r'([a-zéèêëàâäôöûüçîïA-ZÉÈÊËÀÂÄÔÖÛÜÇÎÏ]+)\n([a-zéèêëàâäôöûüçîï]+)',
        r'\1\2',
        markdown_text
    )

    # Pattern 2: word + \n within sentence (not before #, -, etc.)
    # Targets: "word\nword" but not "word\n#", "word\n-", "word\n\n"
    markdown_text = re.sub(
        r'([a-zéèêëàâäôöûüçîï])\n(?=[a-zéèêëàâäôöûüçîï])',
        r'\1',
        markdown_text,
        flags=re.IGNORECASE
    )

    return markdown_text


def clean_markdown_output(markdown_text):
    """
    Final markdown cleanup and normalization.

    Removes:
    - "Glissez pour voir" (French table scroll hint)
    - Lines with only whitespace
    - Trailing spaces on lines

    Normalizes:
    - Multiple blank lines to maximum two

    Args:
        markdown_text (str): Raw markdown content

    Returns:
        str: Cleaned markdown
    """
    # Remove "Glissez pour voir" (under tables)
    markdown_text = re.sub(r'^Glissez pour voir\s*$', '',
                           markdown_text, flags=re.MULTILINE)

    # Remove lines with only spaces
    markdown_text = re.sub(r'^\s+$', '', markdown_text, flags=re.MULTILINE)

    # Clean trailing spaces on lines
    markdown_text = re.sub(r' +$', '', markdown_text, flags=re.MULTILINE)

    # Reduce multiple blank lines
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

    return markdown_text


def remove_first_h1(markdown_text):
    """
    Removes the first H1 heading from the document.

    The title is already in YAML frontmatter, so the first H1
    is typically redundant.

    Args:
        markdown_text (str): Markdown content

    Returns:
        str: Content without first H1
    """
    # Remove first H1 (only once)
    markdown_text = re.sub(r'^#\s+.+$', '', markdown_text,
                           count=1, flags=re.MULTILINE)
    # Clean leading blank lines
    markdown_text = markdown_text.lstrip('\n')
    return markdown_text


def remove_unwanted_links(markdown_text):
    """
    Removes ONLY navigation artifacts and metadata links specific to French sites.

    Removes:
    - "Section intitulée..." links (table of contents anchors)
    - "Fenêtre de terminal" links (terminal window indicators)
    - "Aller au contenu" links (skip to content)
    - Metadata lines (categories, tags, badges)

    Note: Preserves all legitimate content links.

    Args:
        markdown_text (str): Markdown content

    Returns:
        str: Content without navigation artifacts
    """
    # Specific pattern for "Section intitulée" with full link
    # Format: [Section intitulée « Title »](url#anchor)
    markdown_text = re.sub(
        r'^\[Section intitul[eéÃ©]+e[^\]]+\]\([^)]+\)\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Plain text variant (without markdown link)
    markdown_text = re.sub(
        r'^Section intitul[eéÃ©]+e\s+[«"][^»"]+[»"]\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # "Fenêtre de terminal" (terminal window)
    markdown_text = re.sub(
        r'^\[Fen[eêÃª]tre de terminal\]\([^)]+\)\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Remove "Aller au contenu" links that escaped HTML cleaning
    markdown_text = re.sub(
        r'^\[Aller au contenu\]\([^)]+\)\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Remove metadata lines (categories, tags, badges)
    # Pattern: simple words separated by spaces without punctuation
    # (e.g., "docs informationnelle published debutant")
    markdown_text = re.sub(
        r'^[a-zA-Z]+(?:\s+[a-zA-Z]+){2,}\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE
    )

    # Clean multiple blank lines
    markdown_text = re.sub(r'\n\n\n+', '\n\n', markdown_text)

    return markdown_text


def deduplicate_nested_callouts(markdown_text):
    """
    Removes nested/duplicated callout markers from improperly nested blockquotes.

    When HTML callouts are nested, the markdown conversion can create multiple
    levels of blockquotes with the same [!TYPE] marker. This function flattens
    them to a single callout.

    Args:
        markdown_text (str): Markdown text with potentially nested callouts

    Returns:
        str: Markdown text with deduplicated callouts

    Example:
        Input:
            > [!NOTE]
            >
            > > [!NOTE]
            > > Content

        Output:
            > [!NOTE]
            >
            > Content
    """
    lines = markdown_text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this is a callout marker line (> [!TYPE])
        match = re.match(r'^(>+)\s*\[!(\w+)\](.*)$', line)
        if match:
            quote_level = len(match.group(1))
            callout_type = match.group(2)
            title = match.group(3).strip()

            # Look ahead to see if there are nested callouts of the same or different type
            j = i + 1
            skip_nested = False

            # Check next few lines for nested callouts
            while j < len(lines) and j < i + 10:
                next_line = lines[j]
                nested_match = re.match(r'^(>+)\s*\[!(\w+)\](.*)$', next_line)

                if nested_match:
                    nested_level = len(nested_match.group(1))
                    # If we found a nested callout (more > than current)
                    if nested_level > quote_level:
                        # Skip all lines until we find the nested callout
                        skip_nested = True
                        # Adjust i to skip the empty lines before nested callout
                        for k in range(i + 1, j):
                            if lines[k].strip() and not lines[k].startswith('>'):
                                result.append(lines[k])
                        i = j - 1  # Will be incremented at end of loop
                        break
                    else:
                        # Found a same-level or lower-level callout, stop looking
                        break
                elif not next_line.startswith('>'):
                    # Not a blockquote line, stop looking
                    break

                j += 1

            if not skip_nested:
                result.append(line)
        else:
            # Not a callout marker, check if it's a nested blockquote line
            # that should have its nesting level reduced
            nested_match = re.match(r'^(>)\s+(>+)\s*(.*)$', line)
            if nested_match:
                # This is a nested blockquote line, reduce nesting by one level
                reduced_line = f'> {nested_match.group(3)}'
                result.append(reduced_line)
            else:
                result.append(line)

        i += 1

    return '\n'.join(result)


def format_callouts(markdown_text):
    """
    Formats callout blocks to ensure proper Markdown callout syntax.

    Ensures all lines in callout blocks start with > and formats the callout
    marker [!TYPE] correctly. Supports Obsidian and GitHub flavored callout syntax.

    Args:
        markdown_text (str): Markdown text with callout markers

    Returns:
        str: Markdown text with properly formatted callouts

    Example:
        Input:
            > [!NOTE] Important
            > This is a note
            Some content

        Output:
            > [!NOTE] Important
            > This is a note
            >
            > Some content
    """
    lines = markdown_text.split('\n')
    result = []
    in_callout = False
    callout_indent = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if line starts a callout
        if re.match(r'^>\s*\[!(\w+)\]', line):
            in_callout = True
            callout_indent = len(line) - len(line.lstrip('>').lstrip())
            result.append(line)
            i += 1
            continue

        # If we're in a callout
        if in_callout:
            # Check if line is still part of the callout (starts with >)
            if line.startswith('>'):
                result.append(line)
            # Empty line might be part of callout or end it
            elif line.strip() == '':
                # Look ahead to see if next line is part of callout
                if i + 1 < len(lines) and lines[i + 1].startswith('>'):
                    result.append('>')
                else:
                    # End of callout
                    in_callout = False
                    result.append(line)
            # Non-empty line without > - check if it should be part of callout
            elif line.strip() and not line.startswith('#'):
                # If the line is indented or follows a callout, include it
                if i > 0 and result[-1].startswith('>'):
                    result.append(f'> {line}')
                else:
                    # End of callout
                    in_callout = False
                    result.append(line)
            else:
                # End of callout
                in_callout = False
                result.append(line)
        else:
            result.append(line)

        i += 1

    return '\n'.join(result)


def fix_code_blocks(markdown_text):
    """
    Fixes code blocks without proper line breaks.

    Adds newlines after:
    - Shell comments followed by commands
    - Semicolons in one-liners
    - 'then' and 'fi' keywords in bash conditionals

    IMPORTANT: Only processes content inside code blocks (triple backticks)
    to avoid breaking regular text.

    Args:
        markdown_text (str): Markdown with code blocks

    Returns:
        str: Fixed code blocks with proper formatting
    """
    def fix_code_block_content(match):
        """Process a single code block."""
        code_block = match.group(0)

        # Pattern: # comment + command stuck together
        code_block = re.sub(
            r'(#[^\n]+?)(if |sudo |docker|npm|git|curl|ssh|apt|dnf|pip|python|bash)',
            r'\1\n\2',
            code_block
        )

        # After semicolons in one-liners
        code_block = re.sub(r';([a-z])', r';\n\1', code_block)

        # After 'then'
        code_block = re.sub(r'; then([a-z\s])', r'; then\n\1', code_block)

        # After 'fi' (bash keyword)
        code_block = re.sub(r'fi([a-z#\s])', r'fi\n\1', code_block)

        return code_block

    # Only process content inside code blocks (between ```)
    markdown_text = re.sub(
        r'```[\s\S]*?```',
        fix_code_block_content,
        markdown_text
    )

    return markdown_text


# ============================================================
# URL EXTRACTION & CRAWLING
# ============================================================
def parse_sitemap(sitemap_url, filter_path=None):
    """
    Parses sitemap.xml and extracts URLs.

    Supports:
    - Simple sitemaps (<url><loc>...)
    - Sitemap indexes (<sitemap><loc>...)
    - Optional filtering by path prefix

    Args:
        sitemap_url (str): URL of sitemap.xml
        filter_path (str, optional): Path prefix filter (e.g., "/blog/")

    Returns:
        list: List of URLs

    Raises:
        requests.RequestException: If sitemap cannot be fetched
    """
    print(f"📋 Parsing sitemap: {sitemap_url}")

    try:
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()

        # Parse XML with BeautifulSoup
        # Note: Requires lxml (already in requirements.txt)
        soup = BeautifulSoup(response.content, 'xml')

        urls = []

        # Check if it's a sitemap index
        sitemap_tags = soup.find_all('sitemap')
        if sitemap_tags:
            print(f"📦 Sitemap index detected ({len(sitemap_tags)} sitemaps)")
            # Recursive: parse each sub-sitemap
            for sitemap_tag in sitemap_tags:
                loc = sitemap_tag.find('loc')
                if loc and loc.text:
                    sub_urls = parse_sitemap(loc.text.strip(), filter_path)
                    urls.extend(sub_urls)
        else:
            # Simple sitemap: extract URLs
            url_tags = soup.find_all('url')
            print(f"📄 {len(url_tags)} URLs found")

            for url_tag in url_tags:
                loc = url_tag.find('loc')
                if loc and loc.text:
                    url = loc.text.strip()

                    # Filter by path if specified
                    if filter_path:
                        parsed = urlparse(url)
                        if not parsed.path.startswith(filter_path):
                            continue

                    urls.append(url)

        if filter_path:
            print(f"✅ {len(urls)} URLs match filter '{filter_path}'")

        return urls

    except Exception as e:
        print(f"❌ Sitemap parsing error: {e}")
        return []


def extract_links(soup, base_url):
    """
    Extracts all HTTP/HTTPS links from a page.

    Args:
        soup (BeautifulSoup): Parsed HTML document
        base_url (str): Base URL for resolving relative links

    Returns:
        set: Set of absolute URLs (without fragments)
    """
    links = set()

    for anchor in soup.find_all('a', href=True):
        href = anchor['href']

        # Resolve relative links
        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)

        # Filter non-HTTP, mailto, tel, etc.
        if parsed.scheme not in ('http', 'https'):
            continue

        # Remove fragment (#anchor)
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            ''  # No fragment
        ))

        links.add(clean_url)

    return links


# ============================================================
# DATA STRUCTURES
# ============================================================
class URLQueue:
    """
    Manages a URL queue with deduplication and path filtering.

    Attributes:
        urls (list): List of tuples (url, depth)
        visited (set): Set of already visited URLs
        base_domain (str): Domain to restrict crawling to
        base_path (str): Path prefix to respect (e.g., "/blog/")
        max_depth (int): Maximum crawl depth (0 = unlimited)
    """

    def __init__(self, start_url, max_depth=1):
        """
        Initialize URL queue from a starting URL.

        Args:
            start_url (str): Starting URL (defines base domain and path)
            max_depth (int): Maximum crawl depth (default: 1)
        """
        self.urls = []
        self.visited = set()
        self.max_depth = max_depth

        # Extract base path from starting URL
        parsed = urlparse(start_url)
        self.base_domain = parsed.netloc
        self.base_path = parsed.path.rstrip('/') + '/'
        if self.base_path == '//':
            self.base_path = '/'

    def add(self, url, depth=0):
        """
        Adds URL if it passes all filters.

        Filters:
        - Not already visited
        - Same domain
        - Starts with base_path
        - Depth <= max_depth

        Args:
            url (str): URL to add
            depth (int): Depth level of this URL

        Returns:
            bool: True if URL was added, False if filtered out
        """
        # Normalize URL (remove fragment, trailing slash)
        parsed = urlparse(url)
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/'),
            '',  # params
            parsed.query,
            ''   # fragment
        ))

        # Apply filters
        if normalized in self.visited:
            return False

        if parsed.netloc != self.base_domain:
            return False

        # Key filter: path must start with base_path
        if not parsed.path.startswith(self.base_path):
            return False

        if self.max_depth > 0 and depth > self.max_depth:
            return False

        self.urls.append((normalized, depth))
        self.visited.add(normalized)
        return True

    def get_next(self):
        """
        Retrieves next URL from queue (FIFO - Breadth-First Search).

        Returns:
            tuple: (url, depth) or (None, None) if queue is empty
        """
        if self.urls:
            return self.urls.pop(0)
        return None, None

    def is_empty(self):
        """
        Checks if queue is empty.

        Returns:
            bool: True if queue has no more URLs
        """
        return len(self.urls) == 0

    def size(self):
        """
        Returns current queue length.

        Returns:
            int: Number of URLs in queue
        """
        return len(self.urls)


class ScrapeStats:
    """
    Tracks scraping statistics and provides reporting.

    Attributes:
        total (int): Total URLs processed
        successful (int): Successfully scraped URLs
        failed (int): Failed URL attempts
        start_time (datetime): Start time of scraping session
    """

    def __init__(self):
        """Initialize statistics tracker."""
        self.total = 0
        self.successful = 0
        self.failed = 0
        self.start_time = datetime.now()

    def record_success(self):
        """Increments success counter."""
        self.successful += 1

    def record_failure(self):
        """Increments failure counter."""
        self.failed += 1

    def report(self):
        """Prints a summary report of scraping session."""
        duration = datetime.now() - self.start_time
        print(f"\n{'='*60}")
        print("📊 FINAL STATISTICS")
        print(f"{'='*60}")
        print(f"✅ Successful:  {self.successful}/{self.total}")
        print(f"❌ Failed:      {self.failed}/{self.total}")
        print(f"⏱️  Duration:    {duration.total_seconds():.1f}s")
        print(f"{'='*60}")


# ============================================================
# BATCH PROCESSING
# ============================================================
def process_multiple_urls(urls, output_dir, delay=1.0, continue_on_error=True):
    """
    Processes a list of URLs with rate limiting.

    Args:
        urls (list): List of URLs to process
        output_dir (str): Output directory
        delay (float): Delay between requests in seconds (default: 1.0)
        continue_on_error (bool): Continue despite errors (default: True)

    Returns:
        ScrapeStats: Statistics object with results

    Raises:
        Exception: If continue_on_error is False and a scrape fails
    """
    stats = ScrapeStats()
    stats.total = len(urls)

    print(f"\n{'='*60}")
    print(f"📊 PROCESSING {stats.total} URLs")
    print(f"{'='*60}\n")

    for i, url in enumerate(urls, 1):
        print(f"\n{'='*60}")
        print(f"📊 Progress: {i}/{stats.total}")
        print(f"{'='*60}")
        print(f"🔗 {url}")

        try:
            scrape_to_markdown(url, output_dir)
            stats.record_success()
        except Exception as e:
            stats.record_failure()
            print(f"❌ Failed: {e}")
            if not continue_on_error:
                raise

        # Rate limiting (except last URL)
        if i < stats.total and delay > 0:
            print(f"⏳ Waiting {delay}s...")
            time.sleep(delay)

    return stats


def discover_urls_by_path(start_url, max_depth=0, max_urls=0):
    """
    Discovers all URLs under the same path without scraping (lightweight crawl).

    Args:
        start_url (str): Starting URL (defines base path)
        max_depth (int): Maximum crawl depth (0 = unlimited, default: 0)
        max_urls (int): Max URLs to discover (0 = unlimited, default: 0)

    Returns:
        list: List of discovered URLs

    Example:
        >>> urls = discover_urls_by_path("https://example.com/blog/", max_depth=1)
        >>> print(f"Found {len(urls)} URLs")
    """
    queue = URLQueue(start_url, max_depth)
    queue.add(start_url, depth=0)
    discovered = []

    print(f"\n{'='*60}")
    print("🔍 DISCOVERING...")
    print(f"{'='*60}")
    print(f"\n Discovering URLs (crawling without scraping)...")

    while not queue.is_empty():
        # URL limit check
        if max_urls > 0 and len(discovered) >= max_urls:
            break

        url, depth = queue.get_next()
        discovered.append(url)

        try:
            # Only fetch and parse HTML (no markdown conversion)
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract links for next level
            if max_depth == 0 or depth < max_depth:
                links = extract_links(soup, url)
                for link in links:
                    queue.add(link, depth + 1)

            # Progress indicator
            print(
                f"   [{len(discovered)}] URLs discovered (Queue: {queue.size()})...", end='\r')

        except Exception as e:
            # Silently skip failed URLs during discovery
            pass

    print(f"\n✅ Discovery complete: {len(discovered)} URLs found\n")
    return discovered


def crawl_by_path(start_url, output_dir, max_depth=1, delay=1.0, max_urls=0):
    """
    Crawls all pages under the same path as start_url.

    Uses breadth-first search to discover and process pages within
    the same path prefix. Automatically preserves directory structure
    in output.

    Args:
        start_url (str): Starting URL (defines base path)
        output_dir (str): Output directory
        max_depth (int): Maximum crawl depth (0 = unlimited, default: 1)
        delay (float): Delay between requests in seconds (default: 1.0)
        max_urls (int): Max URLs to process (0 = unlimited, default: 0)

    Returns:
        ScrapeStats: Crawling statistics

    Example:
        >>> crawl_by_path("https://example.com/blog/", "./output", max_depth=2)
        # Crawls all pages starting with /blog/ up to 2 levels deep
    """
    queue = URLQueue(start_url, max_depth)
    queue.add(start_url, depth=0)
    stats = ScrapeStats()

    print(f"\n{'='*60}")
    print("🕷️  PATH-BASED CRAWLING")
    print(f"{'='*60}")
    print(f"Starting URL:    {start_url}")
    print(f"Base path:       {queue.base_path}")
    print(f"Max depth:       {max_depth}")
    print(f"{'='*60}\n")

    while not queue.is_empty():
        # URL limit check
        if max_urls > 0 and stats.total >= max_urls:
            print(f"⚠️  Reached limit of {max_urls} URLs")
            break

        url, depth = queue.get_next()
        stats.total += 1

        print(f"\n{'='*60}")
        print(f"📊 [{stats.total}] Depth: {depth} | Queue: {queue.size()}")
        print(f"{'='*60}")
        print(f"🔗 {url}")

        try:
            # Scrape the page
            _, soup = scrape_to_markdown(url, output_dir)
            stats.record_success()

            # Extract links for next level
            if max_depth == 0 or depth < max_depth:
                links = extract_links(soup, url)
                added_count = 0
                for link in links:
                    if queue.add(link, depth + 1):
                        added_count += 1

                print(
                    f"🔗 {len(links)} links found, {added_count} added to queue")

        except Exception as e:
            stats.record_failure()
            print(f"❌ Failed: {e}")

        # Rate limiting
        if not queue.is_empty() and delay > 0:
            print(f"⏳ Waiting {delay}s...")
            time.sleep(delay)

    return stats


# ============================================================
# CORE SCRAPING
# ============================================================
def scrape_to_markdown(url, output_dir='output'):
    """
    Scrapes a URL and converts it to markdown with YAML frontmatter.

    Processing pipeline:
    1. Download HTML with UTF-8 encoding
    2. Parse with BeautifulSoup
    3. Extract title (from <title>, og:title, or <h1>)
    4. Clean HTML (remove nav, footer, ads, etc.)
    5. Convert callouts/admonitions to markdown callout format (deduplicate nested)
    6. Convert relative URLs to absolute
    7. Convert to markdown using markdownify
    8. Post-process (fix broken words, deduplicate callouts, format callouts, clean output, remove artifacts)
    9. Add YAML frontmatter with title, date, source
    10. Save to file with preserved directory structure

    Args:
        url (str): URL of page to scrape
        output_dir (str): Output directory (default: 'output')

    Returns:
        tuple: (Path of created file, BeautifulSoup object)

    Raises:
        requests.RequestException: Network error
        Exception: Processing error
    """

    try:
        # Download page with explicit UTF-8 encoding
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'  # Force UTF-8
        html = response.text

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title = extract_title(soup)
        print(f"📄 Title: {title}")

        # Clean HTML
        soup = clean_html(soup)

        # Convert callouts to markdown format
        soup = convert_callouts_to_markdown(soup)

        # Convert relative links to absolute
        soup = convert_relative_to_absolute_urls(soup, url)

        # Convert to markdown with optimized options
        markdown = md(
            str(soup),
            heading_style="ATX",
            bullets="-",
            code_language="",
            strip=['script', 'style'],
            # IMPORTANT: don't strip links or images
            escape_asterisks=False,
            escape_underscores=False
        )

        # Post-processing
        markdown = fix_broken_words(markdown)
        markdown = fix_code_blocks(markdown)
        markdown = remove_unwanted_links(markdown)
        markdown = deduplicate_nested_callouts(markdown)
        markdown = format_callouts(markdown)
        markdown = clean_markdown_output(markdown)
        markdown = remove_first_h1(markdown)
        # Second pass to repair words that may have been re-broken
        markdown = fix_broken_words(markdown)

        # Add YAML frontmatter
        frontmatter = f"""---
title: {title}
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
source: {url}
---

"""

        markdown = frontmatter + markdown

        # Generate output path with preserved directory structure
        output_path = get_output_path(url, title, output_dir)

        # Create directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save file
        output_path.write_text(markdown, encoding='utf-8')
        print(f"✅ Saved: {output_path}")

        return output_path, soup

    except requests.RequestException as e:
        print(f"❌ Download error: {e}")
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


# ============================================================
# CLI & ENTRY POINT
# ============================================================
def confirm_processing(mode, url_count, output_dir, auto_yes=False):
    """
    Displays processing summary and asks for user confirmation.

    Args:
        mode (str): Processing mode ('batch', 'crawl', 'sitemap')
        url_count (int): Number of URLs to process
        output_dir (str): Output directory path
        auto_yes (bool): Skip confirmation if True (default: False)

    Returns:
        bool: True if user confirms, False otherwise
    """
    print(f"\n{'='*60}")
    print("📋 PROCESSING SUMMARY")
    print(f"{'='*60}")

    if mode == 'crawl':
        print(f"Mode:            Path-based crawling")
        print(f"URLs discovered: {url_count}")
    else:
        print(
            f"Mode:            {'Sitemap' if mode == 'sitemap' else 'Batch'} processing")
        print(f"URLs to process: {url_count}")

    print(f"Output dir:      {output_dir}")
    print(f"{'='*60}\n")

    if auto_yes:
        print("✅ Auto-confirmed (--yes flag)")
        return True

    try:
        response = input("❓ Do you want to proceed? [Y/n]: ").strip().lower()
        if response in ('', 'y', 'yes', 'o', 'oui'):
            print("✅ Processing confirmed\n")
            return True
        else:
            print("❌ Processing cancelled by user")
            return False
    except (KeyboardInterrupt, EOFError):
        print("\n❌ Processing cancelled by user")
        return False


def parse_arguments():
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Web to Markdown Scraper - Converts web pages to markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single URL
  python url2md.py --url https://example.com/article --output ./output

  # Multi-URL
  python url2md.py --url https://example.com/page1 --url https://example.com/page2 -o ./output

  # Path-based crawling
  python url2md.py --crawl --url https://example.com/blog/ --output ./output

  # Crawling with custom depth
  python url2md.py --crawl --max-depth 2 -u https://example.com/blog/ -o ./output

  # From sitemap
  python url2md.py --sitemap --url https://example.com/sitemap.xml --output ./output

  # Sitemap filtered by path
  python url2md.py --sitemap --filter-path "/blog/" -u https://example.com/sitemap.xml -o ./output

  # From text file
  python url2md.py --file urls.txt --output ./output

  # Skip confirmation prompt (for automation)
  python url2md.py --yes --crawl --url https://example.com/blog/ --output ./output
        """
    )

    # URL and output options
    parser.add_argument('-u', '--url', action='append', dest='urls',
                        help='URL to scrape (can be used multiple times)')
    parser.add_argument('-o', '--output', dest='output_dir', default='output',
                        help='Output directory (default: ./output)')

    # Crawling mode
    parser.add_argument('-c', '--crawl', action='store_true',
                        help='Enable path-based crawling from URL')
    parser.add_argument('-d', '--max-depth', type=int, default=1,
                        help='Maximum crawl depth (0=unlimited, default: 1)')

    # Sitemap mode
    parser.add_argument('-s', '--sitemap', action='store_true',
                        help='Parse sitemap.xml to get URLs')
    parser.add_argument('--filter-path', type=str,
                        help='Filter URLs by path prefix (e.g., "/blog/")')

    # URL file input
    parser.add_argument('-f', '--file', type=str,
                        help='Read URLs from text file (one URL per line)')

    # Processing options
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--max-urls', type=int, default=0,
                        help='Maximum number of URLs to process (0=unlimited)')
    parser.add_argument('--continue-on-error', action='store_true', default=True,
                        help='Continue scraping even if some URLs fail')
    parser.add_argument('-y', '--yes', action='store_true',
                        help='Skip confirmation prompt and proceed automatically')

    return parser.parse_args()


def main():
    """
    Main entry point for the script.

    Orchestrates the scraping workflow:
    1. Parse command-line arguments
    2. Collect URLs from various sources (file, sitemap, CLI args)
    3. Validate URLs
    4. Display processing summary and request user confirmation
    5. Execute scraping (batch or crawl mode)
    6. Display final statistics
    """
    args = parse_arguments()

    # Collect URLs from various sources
    urls = []

    # 1. From text file
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                file_urls = [line.strip() for line in f if line.strip()
                             and not line.startswith('#')]
                urls.extend(file_urls)
                print(f"📄 {len(file_urls)} URLs loaded from {args.file}")
        except FileNotFoundError:
            print(f"❌ File not found: {args.file}")
            sys.exit(1)

    # 2. From sitemap
    if args.sitemap:
        if not args.urls:
            print("❌ Please specify sitemap URL")
            sys.exit(1)
        sitemap_urls = parse_sitemap(args.urls[0], args.filter_path)
        urls.extend(sitemap_urls)

    # 3. From CLI arguments
    elif args.urls:
        urls.extend(args.urls)

    # Check that we have at least one URL
    if not urls:
        print("❌ No URLs provided")
        print("\nUse --help to see usage examples")
        sys.exit(1)

    # Validate URLs
    for url in urls:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            print(f"❌ Invalid URL: {url}")
            print("URL must start with http:// or https://")
            sys.exit(1)

    # Show summary and ask for confirmation
    if args.crawl:
        # Crawling mode: discover URLs first to get exact count
        try:
            discovered_urls = discover_urls_by_path(
                urls[0],
                args.max_depth,
                args.max_urls
            )

            # Show exact count after discovery
            confirmed = confirm_processing(
                mode='crawl',
                url_count=len(discovered_urls),
                output_dir=args.output_dir,
                auto_yes=args.yes
            )

            # Replace URL list with discovered URLs for processing
            if confirmed:
                urls = discovered_urls
        except Exception as e:
            print(f"❌ Discovery failed: {e}")
            sys.exit(1)
    else:
        # Batch/sitemap mode: show exact count
        mode = 'sitemap' if args.sitemap else 'batch'
        confirmed = confirm_processing(
            mode=mode,
            url_count=len(urls),
            output_dir=args.output_dir,
            auto_yes=args.yes
        )

    # Exit if user declined
    if not confirmed:
        sys.exit(0)

    # Execute based on mode
    try:
        # Both crawl and batch modes now process a list of URLs
        # (crawl has already discovered the URLs in the previous step)
        stats = process_multiple_urls(
            urls,
            args.output_dir,
            args.delay,
            args.continue_on_error
        )

        # Display final report
        stats.report()
        print("\n🎉 Scraping completed!")

    except KeyboardInterrupt:
        print("\n\n⚠️  User interruption (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
