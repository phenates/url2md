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
    - Navigation elements (nav, header, footer, aside)
    - Scripts and styles
    - Forms, iframes, buttons
    - Common navigation classes (navbar, sidebar, menu, etc.)
    - Advertisement and social sharing widgets
    - Skip-to-content links

    Args:
        soup (BeautifulSoup): Parsed HTML document

    Returns:
        BeautifulSoup: Cleaned soup object
    """
    # Elements to remove by tag name
    unwanted_tags = ['nav', 'header', 'footer', 'aside', 'script', 'style',
                     'iframe', 'noscript', 'button', 'form']

    for tag in unwanted_tags:
        for element in soup.find_all(tag):
            element.decompose()

    # Classes/IDs often related to navigation
    unwanted_classes = ['navigation', 'navbar', 'sidebar', 'menu', 'footer',
                        'header', 'breadcrumb', 'social', 'share', 'cookie',
                        'advertisement', 'ad-', 'banner', 'popup', 'skip',
                        'category', 'tag', 'meta', 'badge']

    for class_name in unwanted_classes:
        for element in soup.find_all(class_=re.compile(class_name, re.I)):
            element.decompose()

    # Remove "skip to content" links
    for link in soup.find_all('a', href=re.compile(r'#.*top|#content|#main', re.I)):
        link.decompose()

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


def fix_code_blocks(markdown_text):
    """
    Fixes code blocks without proper line breaks.

    Adds newlines after:
    - Shell comments followed by commands
    - Semicolons in one-liners
    - 'then' and 'fi' keywords in bash conditionals

    Args:
        markdown_text (str): Markdown with code blocks

    Returns:
        str: Fixed code blocks with proper formatting
    """
    # Pattern: # comment + command stuck together
    markdown_text = re.sub(
        r'(#[^\n]+?)(if |sudo |docker|npm|git|curl|ssh|apt|dnf|pip|python|bash)',
        r'\1\n\2',
        markdown_text
    )

    # After semicolons in one-liners
    markdown_text = re.sub(r';([a-z])', r';\n\1', markdown_text)

    # After 'then'
    markdown_text = re.sub(r'; then([a-z\s])', r'; then\n\1', markdown_text)

    # After 'fi'
    markdown_text = re.sub(r'fi([a-z#\s])', r'fi\n\1', markdown_text)

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
    5. Convert relative URLs to absolute
    6. Convert to markdown using markdownify
    7. Post-process (fix broken words, clean output, remove artifacts)
    8. Add YAML frontmatter with title, date, source
    9. Save to file with preserved directory structure

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
  python url2md.py https://example.com/article ./output

  # Multi-URL
  python url2md.py https://example.com/page1 https://example.com/page2 ./output

  # Path-based crawling
  python url2md.py --crawl https://example.com/blog/ ./output

  # Crawling with custom depth
  python url2md.py --crawl --max-depth 2 https://example.com/blog/ ./output

  # From sitemap
  python url2md.py --sitemap https://example.com/sitemap.xml ./output

  # Sitemap filtered by path
  python url2md.py --sitemap --filter-path "/blog/" https://example.com/sitemap.xml ./output

  # From text file
  python url2md.py --file urls.txt ./output
        """
    )

    # Positional arguments
    parser.add_argument('urls', nargs='*', help='URL(s) to scrape')
    parser.add_argument('output_dir', nargs='?', default='output',
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

    return parser.parse_args()


def main():
    """
    Main entry point for the script.

    Orchestrates the scraping workflow:
    1. Parse command-line arguments
    2. Collect URLs from various sources (file, sitemap, CLI args)
    3. Validate URLs
    4. Execute scraping (batch or crawl mode)
    5. Display final statistics
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

    # Execute based on mode
    try:
        if args.crawl:
            # Crawling mode: uses only first URL as starting point
            stats = crawl_by_path(
                urls[0],
                args.output_dir,
                args.max_depth,
                args.delay,
                args.max_urls
            )
        else:
            # Batch mode: processes all URLs
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
