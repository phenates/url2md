#!/usr/bin/env python3
"""
URL to Markdown Scraper (url2md)
==================================

Convertit des pages web en fichiers markdown a partir de leurs URL, avec support multi-URL,
crawling basé sur path, et parsing de sitemap.xml.

Features:
- Single ou multi-URL scraping
- Crawling basé sur le path (ex: /blog/ → tous les articles du blog)
- Support sitemap.xml avec filtrage
- Structure de dossiers préservée
- Nettoyage HTML intelligent
- Contenu français optimisé

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
    """Convertit un titre en nom de fichier valide."""
    # Enlever les caractères spéciaux
    title = re.sub(r'[^\w\s-]', '', title)
    # Remplacer les espaces par des tirets
    title = re.sub(r'[\s_:]+', '-', title)
    # Tout en minuscules
    title = title.lower().strip('-')
    # Limiter la longueur
    return title[:100] if title else 'untitled'


def get_output_path(url, title, output_dir):
    """
    Génère le chemin de sortie en préservant la structure de l'URL.

    Args:
        url: URL source
        title: Titre de la page (pour nom de fichier)
        output_dir: Dossier de sortie racine

    Returns:
        Path: Chemin complet du fichier à créer

    Exemple:
        url = "https://example.com/blog/2024/article"
        → output_dir/example.com/blog/2024/article.md
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path.strip('/')

    # Early return pour path vide
    if not path:
        filename = sanitize_filename(
            title if title != 'untitled' else 'index') + '.md'
        return Path(output_dir) / domain / filename

    # Extraire dossiers et nom de base
    path_parts = path.split('/')
    dir_parts = path_parts[:-1]
    file_base = path_parts[-1] or 'index'

    # Construire le chemin
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
    """Extrait le titre de la page (essaie plusieurs méthodes)."""
    # 1. Balise <title>
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    # 2. Meta og:title
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()

    # 3. Premier <h1>
    h1 = soup.find('h1')
    if h1:
        return h1.get_text().strip()

    # 4. Fallback sur l'URL
    return "untitled"


def convert_relative_to_absolute_urls(soup, base_url):
    """Convertit tous les liens relatifs en liens absolus."""
    # Convertir les liens href (balises <a>)
    for link in soup.find_all('a', href=True):
        link['href'] = urljoin(base_url, link['href'])

    # Convertir les images src (balises <img>)
    for img in soup.find_all('img', src=True):
        img['src'] = urljoin(base_url, img['src'])

    # Convertir les sources srcset (images responsive)
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
    """Nettoie le HTML avant conversion (enlève nav, footer, etc.)."""
    # Éléments à supprimer
    unwanted_tags = ['nav', 'header', 'footer', 'aside', 'script', 'style',
                     'iframe', 'noscript', 'button', 'form']

    for tag in unwanted_tags:
        for element in soup.find_all(tag):
            element.decompose()

    # Classes/IDs souvent liées à la navigation
    unwanted_classes = ['navigation', 'navbar', 'sidebar', 'menu', 'footer',
                        'header', 'breadcrumb', 'social', 'share', 'cookie',
                        'advertisement', 'ad-', 'banner', 'popup', 'skip',
                        'category', 'tag', 'meta', 'badge']

    for class_name in unwanted_classes:
        for element in soup.find_all(class_=re.compile(class_name, re.I)):
            element.decompose()

    # Supprimer les liens "skip to content" / "aller au contenu"
    for link in soup.find_all('a', href=re.compile(r'#.*top|#content|#main', re.I)):
        link.decompose()

    return soup


# ============================================================
# MARKDOWN CLEANUP
# ============================================================
def fix_broken_words(markdown_text):
    """Répare les mots coupés au milieu par des retours à la ligne."""
    # Réparer les mots coupés: mot suivi d'un retour à la ligne puis d'autres lettres
    # Pattern: lettre(s) + retour à la ligne + lettre(s) minuscules (sans espace avant)
    # Exemples: "effi\ncace" -> "efficace", "Dockerfi\nle" -> "Dockerfile"

    # Pattern 1: lettres + \n + lettres (cas général)
    markdown_text = re.sub(
        r'([a-zéèêëàâäôöûüçîïA-ZÉÈÊËÀÂÄÔÖÛÜÇÎÏ]+)\n([a-zéèêëàâäôöûüçîï]+)',
        r'\1\2',
        markdown_text
    )

    # Pattern 2: mot + \n au milieu d'une phrase (pas avant un titre #, liste -, etc.)
    # Cible: "mot\nmot" mais pas "mot\n#", "mot\n-", "mot\n\n"
    markdown_text = re.sub(
        r'([a-zéèêëàâäôöûüçîï])\n(?=[a-zéèêëàâäôöûüçîï])',
        r'\1',
        markdown_text,
        flags=re.IGNORECASE
    )

    return markdown_text


def clean_markdown_output(markdown_text):
    """Nettoyage final du markdown."""
    # Supprimer "Glissez pour voir" (sous les tableaux)
    markdown_text = re.sub(r'^Glissez pour voir\s*$', '',
                           markdown_text, flags=re.MULTILINE)

    # Supprimer les lignes avec juste des espaces
    markdown_text = re.sub(r'^\s+$', '', markdown_text, flags=re.MULTILINE)

    # Nettoyer les espaces en fin de ligne
    markdown_text = re.sub(r' +$', '', markdown_text, flags=re.MULTILINE)

    # Réduire les lignes vides multiples
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

    return markdown_text


def remove_first_h1(markdown_text):
    """Supprime le premier titre H1 du document."""
    # Supprimer le premier H1 (une seule fois)
    markdown_text = re.sub(r'^#\s+.+$', '', markdown_text,
                           count=1, flags=re.MULTILINE)
    # Nettoyer les lignes vides au début
    markdown_text = markdown_text.lstrip('\n')
    return markdown_text


def remove_unwanted_links(markdown_text):
    """Supprime UNIQUEMENT les liens Section intitulée et Fenêtre de terminal."""

    # Pattern spécifique pour Section intitulée avec lien complet
    # Format: [Section intitulée « Titre »](url#anchor)
    markdown_text = re.sub(
        r'^\[Section intitul[eéÃ©]+e[^\]]+\]\([^)]+\)\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Variante texte seul (sans markdown link)
    markdown_text = re.sub(
        r'^Section intitul[eéÃ©]+e\s+[«"][^»"]+[»"]\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Fenêtre de terminal
    markdown_text = re.sub(
        r'^\[Fen[eêÃª]tre de terminal\]\([^)]+\)\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Supprimer les liens "Aller au contenu" qui ont échappé au nettoyage HTML
    markdown_text = re.sub(
        r'^\[Aller au contenu\]\([^)]+\)\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Supprimer les lignes de métadonnées (catégories, tags, badges)
    # Pattern: mots simples séparés par espaces sans ponctuation
    # (ex: "docs informationnelle published debutant")
    markdown_text = re.sub(
        r'^[a-zA-Z]+(?:\s+[a-zA-Z]+){2,}\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE
    )

    # Nettoyer les lignes vides multiples
    markdown_text = re.sub(r'\n\n\n+', '\n\n', markdown_text)

    return markdown_text


def fix_code_blocks(markdown_text):
    """Corrige les code blocks sans sauts de ligne."""
    # Pattern : # commentaire + commande collée
    markdown_text = re.sub(
        r'(#[^\n]+?)(if |sudo |docker|npm|git|curl|ssh|apt|dnf|pip|python|bash)',
        r'\1\n\2',
        markdown_text
    )

    # Après ; dans les one-liners
    markdown_text = re.sub(r';([a-z])', r';\n\1', markdown_text)

    # Après 'then'
    markdown_text = re.sub(r'; then([a-z\s])', r'; then\n\1', markdown_text)

    # Après 'fi'
    markdown_text = re.sub(r'fi([a-z#\s])', r'fi\n\1', markdown_text)

    return markdown_text


# ============================================================
# URL EXTRACTION & CRAWLING
# ============================================================
def parse_sitemap(sitemap_url, filter_path=None):
    """
    Parse un sitemap.xml et extrait les URLs.

    Supporte:
    - Sitemaps simples (<url><loc>...)
    - Sitemap indexes (<sitemap><loc>...)
    - Filtrage optionnel par préfixe de path

    Args:
        sitemap_url: URL du sitemap.xml
        filter_path: Préfixe de path optionnel (ex: "/blog/")

    Returns:
        list: Liste d'URLs
    """
    print(f"📋 Parsing du sitemap: {sitemap_url}")

    try:
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()

        # Parser XML avec BeautifulSoup
        # Note: Nécessite lxml (déjà dans requirements.txt)
        soup = BeautifulSoup(response.content, 'xml')

        urls = []

        # Vérifier si c'est un sitemap index
        sitemap_tags = soup.find_all('sitemap')
        if sitemap_tags:
            print(f"📦 Sitemap index détecté ({len(sitemap_tags)} sitemaps)")
            # Récursif: parser chaque sub-sitemap
            for sitemap_tag in sitemap_tags:
                loc = sitemap_tag.find('loc')
                if loc and loc.text:
                    sub_urls = parse_sitemap(loc.text.strip(), filter_path)
                    urls.extend(sub_urls)
        else:
            # Sitemap simple: extraire les URLs
            url_tags = soup.find_all('url')
            print(f"📄 {len(url_tags)} URLs trouvées")

            for url_tag in url_tags:
                loc = url_tag.find('loc')
                if loc and loc.text:
                    url = loc.text.strip()

                    # Filtrer par path si spécifié
                    if filter_path:
                        parsed = urlparse(url)
                        if not parsed.path.startswith(filter_path):
                            continue

                    urls.append(url)

        if filter_path:
            print(f"✅ {len(urls)} URLs correspondent au filtre '{filter_path}'")

        return urls

    except Exception as e:
        print(f"❌ Erreur de parsing du sitemap: {e}")
        return []


def extract_links(soup, base_url):
    """
    Extrait tous les liens HTTP/HTTPS d'une page.

    Args:
        soup: BeautifulSoup object
        base_url: URL de base pour résoudre les liens relatifs

    Returns:
        set: Ensemble d'URLs absolues
    """
    links = set()

    for anchor in soup.find_all('a', href=True):
        href = anchor['href']

        # Résoudre liens relatifs
        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)

        # Filtrer non-HTTP, mailto, tel, etc.
        if parsed.scheme not in ('http', 'https'):
            continue

        # Enlever le fragment (#anchor)
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            ''  # Pas de fragment
        ))

        links.add(clean_url)

    return links


# ============================================================
# SECTION 6: DATA STRUCTURES
# ============================================================
class URLQueue:
    """
    Gère une queue d'URLs avec déduplication et filtrage par path.

    Attributes:
        urls: Liste de tuples (url, depth)
        visited: Set des URLs déjà visitées
        base_path: Préfixe de path à respecter (ex: "/blog/")
        max_depth: Profondeur maximale
    """

    def __init__(self, start_url, max_depth=1):
        self.urls = []
        self.visited = set()
        self.max_depth = max_depth

        # Extraire le base path de l'URL de départ
        parsed = urlparse(start_url)
        self.base_domain = parsed.netloc
        self.base_path = parsed.path.rstrip('/') + '/'
        if self.base_path == '//':
            self.base_path = '/'

    def add(self, url, depth=0):
        """
        Ajoute une URL si elle passe les filtres.

        Filtres:
        - Pas déjà visitée
        - Même domaine
        - Commence par le base_path
        - Profondeur <= max_depth
        """
        # Normaliser URL (enlever fragment, trailing slash)
        parsed = urlparse(url)
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/'),
            '',  # params
            parsed.query,
            ''   # fragment
        ))

        # Filtres
        if normalized in self.visited:
            return False

        if parsed.netloc != self.base_domain:
            return False

        # Filtre clé: path doit commencer par base_path
        if not parsed.path.startswith(self.base_path):
            return False

        if self.max_depth > 0 and depth > self.max_depth:
            return False

        self.urls.append((normalized, depth))
        self.visited.add(normalized)
        return True

    def get_next(self):
        """Récupère la prochaine URL (FIFO - Breadth-First Search)."""
        if self.urls:
            return self.urls.pop(0)
        return None, None

    def is_empty(self):
        """Vérifie si la queue est vide"""
        return len(self.urls) == 0

    def size(self):
        """Retourne la longueur de la queue"""
        return len(self.urls)


class ScrapeStats:
    """Suivi des statistiques de scraping."""

    def __init__(self):
        self.total = 0
        self.successful = 0
        self.failed = 0
        self.start_time = datetime.now()

    def record_success(self):
        """Incremente le compteur de succès."""
        self.successful += 1

    def record_failure(self):
        """Incremente le compteur d'échec."""
        self.failed += 1

    def report(self):
        """Affiche un résumé."""
        duration = datetime.now() - self.start_time
        print(f"\n{'='*60}")
        print("📊 STATISTIQUES FINALES")
        print(f"{'='*60}")
        print(f"✅ Succès:      {self.successful}/{self.total}")
        print(f"❌ Échecs:      {self.failed}/{self.total}")
        print(f"⏱️  Durée:       {duration.total_seconds():.1f}s")
        print(f"{'='*60}")


# ============================================================
# BATCH PROCESSING
# ============================================================
def process_multiple_urls(urls, output_dir, delay=1.0, continue_on_error=True):
    """
    Traite une liste d'URLs avec rate limiting.

    Args:
        urls: Liste d'URLs
        output_dir: Dossier de sortie
        delay: Délai entre requêtes
        continue_on_error: Continue malgré les erreurs

    Returns:
        ScrapeStats: Statistiques
    """
    stats = ScrapeStats()
    stats.total = len(urls)

    print(f"\n{'='*60}")
    print(f"📊 TRAITEMENT DE {stats.total} URLs")
    print(f"{'='*60}\n")

    for i, url in enumerate(urls, 1):
        print(f"\n{'='*60}")
        print(f"📊 Progression: {i}/{stats.total}")
        print(f"{'='*60}")
        print(f"🔗 {url}")

        try:
            scrape_to_markdown(url, output_dir)
            stats.record_success()
        except Exception as e:
            stats.record_failure()
            print(f"❌ Échec: {e}")
            if not continue_on_error:
                raise

        # Rate limiting (sauf dernière URL)
        if i < stats.total and delay > 0:
            print(f"⏳ Pause de {delay}s...")
            time.sleep(delay)

    return stats


def crawl_by_path(start_url, output_dir, max_depth=1, delay=1.0, max_urls=0):
    """
    Crawle toutes les pages sous le même path que start_url.

    Args:
        start_url: URL de départ (définit le base path)
        output_dir: Dossier de sortie
        max_depth: Profondeur maximale
        delay: Délai entre requêtes
        max_urls: Max URLs à traiter (0 = illimité)

    Returns:
        ScrapeStats: Statistiques du crawling
    """
    queue = URLQueue(start_url, max_depth)
    queue.add(start_url, depth=0)
    stats = ScrapeStats()

    print(f"\n{'='*60}")
    print("🕷️  CRAWLING BASÉ SUR LE PATH")
    print(f"{'='*60}")
    print(f"URL de départ:   {start_url}")
    print(f"Base path:       {queue.base_path}")
    print(f"Profondeur max:  {max_depth}")
    print(f"{'='*60}\n")

    while not queue.is_empty():
        # Limite d'URLs
        if max_urls > 0 and stats.total >= max_urls:
            print(f"⚠️  Limite de {max_urls} URLs atteinte")
            break

        url, depth = queue.get_next()
        stats.total += 1

        print(f"\n{'='*60}")
        print(f"📊 [{stats.total}] Profondeur: {depth} | File: {queue.size()}")
        print(f"{'='*60}")
        print(f"🔗 {url}")

        try:
            # Scraper la page
            _, soup = scrape_to_markdown(url, output_dir)
            stats.record_success()

            # Extraire liens pour le prochain niveau
            if max_depth == 0 or depth < max_depth:
                links = extract_links(soup, url)
                added_count = 0
                for link in links:
                    if queue.add(link, depth + 1):
                        added_count += 1

                print(
                    f"🔗 {len(links)} liens trouvés, {added_count} ajoutés à la file")

        except Exception as e:
            stats.record_failure()
            print(f"❌ Échec: {e}")

        # Rate limiting
        if not queue.is_empty() and delay > 0:
            print(f"⏳ Pause de {delay}s...")
            time.sleep(delay)

    return stats


# ============================================================
# CORE SCRAPING
# ============================================================
def scrape_to_markdown(url, output_dir='output'):
    """
    Scrape une URL et convertit en markdown.

    Args:
        url: URL de la page à scraper
        output_dir: Répertoire de sortie
        quiet: Mode silencieux (moins de logs)

    Returns:
        tuple: (Path du fichier créé, BeautifulSoup object)

    Raises:
        requests.RequestException: Erreur réseau
        Exception: Erreur de traitement
    """

    try:
        # Télécharger la page avec encodage UTF-8 explicite
        # print(f"📥 Téléchargement de {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'  # Forcer UTF-8
        html = response.text

        # Parser avec BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Extraire le titre
        title = extract_title(soup)
        print(f"📄 Titre: {title}")

        # Nettoyer le HTML
        soup = clean_html(soup)

        # Convertir les liens relatifs en liens absolus
        # print("🔗 Conversion des liens relatifs en liens absolus...")
        soup = convert_relative_to_absolute_urls(soup, url)

        # Convertir en markdown avec options optimisées
        # print("🔄 Conversion en markdown...")
        markdown = md(
            str(soup),
            heading_style="ATX",
            bullets="-",
            code_language="",
            strip=['script', 'style'],
            # IMPORTANT: ne pas strip les liens ni images
            escape_asterisks=False,
            escape_underscores=False
        )

        # Post-traitement
        markdown = fix_broken_words(markdown)
        markdown = fix_code_blocks(markdown)
        markdown = remove_unwanted_links(markdown)
        markdown = clean_markdown_output(markdown)
        markdown = remove_first_h1(markdown)
        # Deuxième passage pour réparer les mots qui pourraient avoir été recoupés
        markdown = fix_broken_words(markdown)

        # Ajouter frontmatter YAML
        frontmatter = f"""---
title: {title}
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
source: {url}
---

"""

        markdown = frontmatter + markdown

        # Créer le nom de fichier
        # filename = sanitize_filename(title) + '.md'
        # output_path = Path(output_dir) / filename
        output_path = get_output_path(url, title, output_dir)

        # Créer le répertoire si nécessaire
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Sauvegarder
        output_path.write_text(markdown, encoding='utf-8')
        print(f"✅ Sauvegardé: {output_path}")

        return output_path, soup

    except requests.RequestException as e:
        print(f"❌ Erreur de téléchargement: {e}")
        raise
    except Exception as e:
        print(f"❌ Erreur: {e}")
        raise


# ============================================================
# CLI & ENTRY POINT
# ============================================================
def parse_arguments():
    """Parse les arguments de ligne de commande."""
    parser = argparse.ArgumentParser(
        description='Web to Markdown Scraper - Convertit des pages web en markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  # Single URL
  python url2md.py https://example.com/article ./output

  # Multi-URL
  python url2md.py https://example.com/page1 https://example.com/page2 ./output

  # Crawling basé sur le path
  python url2md.py --crawl https://example.com/blog/ ./output

  # Crawling avec profondeur personnalisée
  python url2md.py --crawl --max-depth 2 https://example.com/blog/ ./output

  # Depuis sitemap
  python url2md.py --sitemap https://example.com/sitemap.xml ./output

  # Sitemap filtré par path
  python url2md.py --sitemap --filter-path "/blog/" https://example.com/sitemap.xml ./output

  # Depuis fichier texte
  python url2md.py --file urls.txt ./output
        """
    )

    # Arguments positionnels
    parser.add_argument('urls', nargs='*', help='URL(s) à scraper')
    parser.add_argument('output_dir', nargs='?', default='output',
                        help='Répertoire de sortie (défaut:  ./output)')

    # Mode crawling
    parser.add_argument('-c', '--crawl', action='store_true',
                        help='Active le crawling basé sur le path de l\'URL')
    parser.add_argument('-d', '--max-depth', type=int, default=1,
                        help='Profondeur maximale de crawling (0=illimité, défaut: 1)')

    # Mode sitemap
    parser.add_argument('-s', '--sitemap', action='store_true',
                        help='Parse sitemap.xml pour obtenir les URLs')
    parser.add_argument('--filter-path', type=str,
                        help='Filtre les URLs par préfixe de path (ex: "/blog/")')

    # Fichier d'URLs
    parser.add_argument('-f', '--file', type=str,
                        help='Lire les URLs depuis un fichier texte (une URL par ligne)')

    # Options de traitement
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Délai entre les requêtes en secondes (défaut: 1.0)')
    parser.add_argument('--max-urls', type=int, default=0,
                        help='Nombre maximum d\'URLs à traiter (0=illimité)')
    parser.add_argument('--continue-on-error', action='store_true', default=True,
                        help='Continue le scraping même si certaines URLs échouent')

    return parser.parse_args()


def main():
    """Point d'entrée du script."""
    args = parse_arguments()

    # Collecter les URLs depuis différentes sources
    urls = []

    # 1. Depuis fichier texte
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                file_urls = [line.strip() for line in f if line.strip()
                             and not line.startswith('#')]
                urls.extend(file_urls)
                print(f"📄 {len(file_urls)} URLs chargées depuis {args.file}")
        except FileNotFoundError:
            print(f"❌ Fichier non trouvé: {args.file}")
            sys.exit(1)

    # 2. Depuis sitemap
    if args.sitemap:
        if not args.urls:
            print("❌ Veuillez spécifier l'URL du sitemap")
            sys.exit(1)
        sitemap_urls = parse_sitemap(args.urls[0], args.filter_path)
        urls.extend(sitemap_urls)

    # 3. Depuis arguments CLI
    elif args.urls:
        urls.extend(args.urls)

    # Vérifier qu'on a au moins une URL
    if not urls:
        print("❌ Aucune URL fournie")
        print("\nUtilisez --help pour voir les exemples d'utilisation")
        sys.exit(1)

    # Valider les URLs
    for url in urls:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            print(f"❌ URL invalide: {url}")
            print("L'URL doit commencer par http:// ou https://")
            sys.exit(1)

    # Exécuter selon le mode
    try:
        if args.crawl:
            # Mode crawling: utilise seulement la première URL comme point de départ
            stats = crawl_by_path(
                urls[0],
                args.output_dir,
                args.max_depth,
                args.delay,
                args.max_urls
            )
        else:
            # Mode batch: traite toutes les URLs
            stats = process_multiple_urls(
                urls,
                args.output_dir,
                args.delay,
                args.continue_on_error
            )

        # Afficher le rapport final
        stats.report()
        print("\n🎉 Scraping terminé !")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interruption utilisateur (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
