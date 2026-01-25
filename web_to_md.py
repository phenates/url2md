#!/usr/bin/env python3
"""
Web to Markdown Scraper
Convertit une page web en fichier markdown avec le titre comme nom de fichier.

Usage:
    python web_to_md.py <url> [output_dir]
    
Exemples:
    python web_to_md.py https://example.com/article
    python web_to_md.py https://example.com/article ./output
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


def sanitize_filename(title):
    """Convertit un titre en nom de fichier valide."""
    # Enlever les caractères spéciaux
    title = re.sub(r'[^\w\s-]', '', title)
    # Remplacer les espaces par des tirets
    title = re.sub(r'[\s_]+', '-', title)
    # Tout en minuscules
    title = title.lower().strip('-')
    # Limiter la longueur
    return title[:100] if title else 'untitled'


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
    # Pattern: mots simples séparés par espaces sans ponctuation (ex: "docs informationnelle published debutant")
    markdown_text = re.sub(
        r'^[a-zA-Z]+(?:\s+[a-zA-Z]+){2,}\s*$',
        '',
        markdown_text,
        flags=re.MULTILINE
    )

    # Nettoyer les lignes vides multiples
    markdown_text = re.sub(r'\n\n\n+', '\n\n', markdown_text)

    return markdown_text


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
    markdown_text = re.sub(r'^#\s+.+$', '', markdown_text, count=1, flags=re.MULTILINE)
    # Nettoyer les lignes vides au début
    markdown_text = markdown_text.lstrip('\n')
    return markdown_text


def scrape_to_markdown(url, output_dir='.'):
    """
    Scrape une URL et convertit en markdown.

    Args:
        url: URL de la page à scraper
        output_dir: Répertoire de sortie (défaut: répertoire courant)

    Returns:
        Path: Chemin du fichier créé
    """
    print(f"📥 Téléchargement de {url}...")

    try:
        # Télécharger la page avec encodage UTF-8 explicite
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
        print("🔗 Conversion des liens relatifs en liens absolus...")
        soup = convert_relative_to_absolute_urls(soup, url)

        # Convertir en markdown avec options optimisées
        print("🔄 Conversion en markdown...")
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
scraped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

"""

        markdown = frontmatter + markdown

        # Créer le nom de fichier
        filename = sanitize_filename(title) + '.md'
        output_path = Path(output_dir) / filename

        # Créer le répertoire si nécessaire
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Sauvegarder
        output_path.write_text(markdown, encoding='utf-8')
        print(f"✅ Sauvegardé: {output_path}")

        return output_path

    except requests.RequestException as e:
        print(f"❌ Erreur de téléchargement: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erreur: {e}")
        sys.exit(1)


def main():
    """Point d'entrée du script."""
    if len(sys.argv) < 2:
        print("❌ Usage: python web_to_md.py <url> [output_dir]")
        print("\nExemples:")
        print("  python web_to_md.py https://example.com/article")
        print("  python web_to_md.py https://example.com/article ./output")
        sys.exit(1)

    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './output'

    # Valider l'URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        print(f"❌ URL invalide: {url}")
        print("L'URL doit commencer par http:// ou https://")
        sys.exit(1)

    # Scraper
    output_file = scrape_to_markdown(url, output_dir)

    print(f"\n🎉 Terminé ! Fichier créé: {output_file.absolute()}")


if __name__ == "__main__":
    main()
