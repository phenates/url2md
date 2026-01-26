# url2md - Web to Markdown Scraper

A powerful Python script that converts web pages to clean markdown files with YAML frontmatter. Features multi-URL processing, path-based crawling, and sitemap.xml parsing.

## ✨ Features

- **Single & Multi-URL scraping** - Process one or multiple URLs at once
- **Path-based crawling** - Automatically discover and scrape all pages under a specific path (e.g., `/blog/`)
- **Sitemap support** - Extract URLs from sitemap.xml with optional path filtering
- **Intelligent HTML cleaning** - Removes navigation, ads, social widgets, and clutter
- **Link preservation** - Converts all relative URLs to absolute URLs
- **Directory structure preservation** - Maintains the original site's folder hierarchy
- **User confirmation** - Shows exact URL count before processing
- **Optimized for French content** - Handles French characters and common French site patterns
- **Rate limiting** - Configurable delay between requests to be respectful

## 📋 Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## 🚀 Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd url2md
```

2. Create and activate a virtual environment:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## 📖 Usage

### Basic Syntax

```bash
python url2md.py [OPTIONS] <url(s)> [output_dir]
```

### Single URL

Scrape a single web page:

```bash
python url2md.py https://example.com/article ./output
```

### Multiple URLs

Process multiple URLs in one run:

```bash
python url2md.py https://example.com/page1 https://example.com/page2 ./output
```

### Path-Based Crawling (`--crawl`)

Automatically discover and scrape all pages under a specific path:

```bash
# Crawl all pages under /blog/
python url2md.py --crawl https://example.com/blog/ ./output

# Crawl with custom depth (0 = unlimited)
python url2md.py --crawl --max-depth 2 https://example.com/blog/ ./output

# Limit the number of URLs
python url2md.py --crawl --max-urls 50 https://example.com/docs/ ./output
```

**How it works:**
1. 🔍 **Discovery phase** - Crawls the site to find all URLs under the base path
2. 📋 **Confirmation** - Shows exact number of URLs found and asks for confirmation
3. ✅ **Processing** - Scrapes and converts all discovered URLs to markdown

### Sitemap Processing (`--sitemap`)

Extract URLs from a sitemap.xml:

```bash
# Process all URLs from sitemap
python url2md.py --sitemap https://example.com/sitemap.xml ./output

# Filter by path prefix
python url2md.py --sitemap --filter-path "/blog/" https://example.com/sitemap.xml ./output
```

### From Text File (`--file`)

Read URLs from a text file (one URL per line):

```bash
python url2md.py --file urls.txt ./output
```

**Example `urls.txt`:**
```
https://example.com/page1
https://example.com/page2
# This is a comment (ignored)
https://example.com/page3
```

## ⚙️ Options

| Option                | Short | Description                                     | Default |
| --------------------- | ----- | ----------------------------------------------- | ------- |
| `--crawl`             | `-c`  | Enable path-based crawling                      | `false` |
| `--max-depth`         | `-d`  | Maximum crawl depth (0=unlimited)               | `1`     |
| `--sitemap`           | `-s`  | Parse sitemap.xml for URLs                      | `false` |
| `--filter-path`       |       | Filter sitemap URLs by path prefix              | None    |
| `--file`              | `-f`  | Read URLs from text file                        | None    |
| `--delay`             |       | Delay between requests (seconds)                | `1.0`   |
| `--max-urls`          |       | Maximum number of URLs to process (0=unlimited) | `0`     |
| `--continue-on-error` |       | Continue scraping if some URLs fail             | `true`  |
| `--yes`               | `-y`  | Skip confirmation prompt (for automation)       | `false` |

## 📁 Output Format

Each scraped page is saved as a markdown file with YAML frontmatter:

```markdown
---
title: Page Title
created: 2026-01-26 12:34:56
source: https://example.com/article
---

# Page Content

The content of the page converted to markdown...
```

### Directory Structure

The script preserves the original URL structure:

```
output/
└── example.com/
    ├── index.md
    └── blog/
        ├── 2024/
        │   ├── article-1.md
        │   └── article-2.md
        └── 2025/
            └── article-3.md
```

## 🎯 Use Cases

### Documentation Archival

Save entire documentation sites locally:

```bash
python url2md.py --crawl --max-depth 3 https://docs.example.com/ ./docs-backup
```

### Blog Migration

Export all blog posts for migration:

```bash
python url2md.py --sitemap --filter-path "/blog/" https://myblog.com/sitemap.xml ./blog-export
```

### Research Collection

Gather articles for offline reading:

```bash
python url2md.py --file research-links.txt ./research
```

### Automated Scraping

Skip confirmation for scripts and automation:

```bash
python url2md.py --yes --crawl https://example.com/news/ ./daily-news
```

## 🛠️ How It Works

### Processing Pipeline

1. **Download** - Fetch HTML with UTF-8 encoding
2. **Parse** - Parse HTML using BeautifulSoup
3. **Extract Title** - Try `<title>`, `og:title`, first `<h1>`, or fallback to "untitled"
4. **Clean HTML** - Remove navigation, ads, scripts, social widgets
5. **Convert Links** - Make all relative URLs absolute
6. **Markdownify** - Convert cleaned HTML to markdown
7. **Post-Process** - Fix broken words, clean output, remove artifacts
8. **Save** - Add YAML frontmatter and save with preserved directory structure

### HTML Cleaning

The script intelligently removes:
- Navigation elements (nav, header, footer, aside)
- Scripts and styles
- Forms, iframes, buttons
- Advertisement and social sharing widgets
- Common CSS classes: navbar, sidebar, menu, breadcrumb, cookie banners
- Skip-to-content links

### Post-Processing

- **Fix broken words** - Repairs words split across lines (e.g., "effi\ncace" → "efficace")
- **Fix code blocks** - Adds proper newlines in shell commands
- **Remove artifacts** - Strips French navigation patterns ("Section intitulée", "Fenêtre de terminal")
- **Clean output** - Removes trailing spaces and reduces multiple blank lines
- **Remove first H1** - Title is already in frontmatter

## 📊 Statistics

After processing, the script displays a summary:

```
============================================================
📊 FINAL STATISTICS
============================================================
✅ Successful:  45/50
❌ Failed:      5/50
⏱️  Duration:    127.3s
============================================================
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 🙏 Acknowledgments

- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
- [markdownify](https://github.com/matthewwithanm/python-markdownify) - HTML to Markdown conversion
- [requests](https://requests.readthedocs.io/) - HTTP library

## 📌 Tips

### Respect Robots.txt

Always check and respect the site's `robots.txt` before large-scale scraping.

### Rate Limiting

Use the `--delay` option to be respectful to the server:

```bash
python url2md.py --crawl --delay 2.0 https://example.com/docs/ ./output
```

### Handling Large Sites

For very large sites, use `--max-urls` to limit processing:

```bash
python url2md.py --crawl --max-urls 100 https://bigsite.com/docs/ ./output
```

### Debugging Failed URLs

Set `--continue-on-error` to false to stop on first error:

```bash
python url2md.py --continue-on-error=false https://example.com/page ./output
```

## 🐛 Troubleshooting

### "Connection timeout" errors

Increase the timeout in the source code or add delays:
```bash
python url2md.py --delay 2.0 <url> ./output
```

### Empty output files

The site may be heavily JavaScript-dependent. This script works best with server-rendered HTML.

### Missing content

Some content may be removed by the HTML cleaning. Check the `clean_html()` function to adjust filters.

### Unicode/encoding issues

The script forces UTF-8 encoding, but some sites may have issues. Check the source page's encoding.

## 🔮 Future Enhancements

- [ ] JavaScript rendering support (Selenium/Playwright)
- [ ] Custom CSS selector support for content extraction
- [ ] HTML output option
- [ ] Image downloading and local storage
- [ ] Configuration file support
- [ ] Parallel processing for faster scraping
- [ ] Resume capability for interrupted sessions

---

**Happy scraping! 🎉**
