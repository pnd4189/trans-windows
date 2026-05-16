#!/usr/bin/env python3
"""EPUB to TXT converter with chapter structure preservation."""

import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Tuple


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML."""

    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list):
        if tag in ('script', 'style'):
            self._skip = True

    def handle_endtag(self, tag: str):
        if tag in ('script', 'style'):
            self._skip = False
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text.append('\n')

    def handle_data(self, data: str):
        if not self._skip:
            self.text.append(data)

    def get_text(self) -> str:
        return ''.join(self.text)


def extract_text_from_html(html_content: str) -> str:
    extractor = HTMLTextExtractor()
    extractor.feed(html_content)
    text = extractor.get_text()
    return re.sub(r'\n\s*\n', '\n\n', text).strip()


def get_epub_chapters(epub_path: str) -> List[Tuple[str, str]]:
    """Extract chapters from EPUB. Returns (title, text) tuples."""
    chapters: List[Tuple[str, str]] = []

    with zipfile.ZipFile(epub_path, 'r') as epub:
        # Find content.opf
        opf_path = None
        for name in epub.namelist():
            if name.endswith('.opf'):
                opf_path = name
                break

        if not opf_path:
            print("Error: No OPF file found in EPUB", file=sys.stderr)
            return []

        opf_content = epub.read(opf_path).decode('utf-8')

        # Extract manifest items
        manifest: dict[str, str] = {}
        for match in re.finditer(r'<item\s+id="([^"]+)"\s+href="([^"]+)"', opf_content):
            manifest[match.group(1)] = match.group(2)

        # Extract spine order
        spine_items = re.findall(r'<itemref\s+idref="([^"]+)"', opf_content)

        base_path = str(Path(opf_path).parent)
        chapter_num = 0

        for item_id in spine_items:
            if item_id not in manifest:
                continue

            href = manifest[item_id]
            file_path = f"{base_path}/{href}" if base_path else href

            try:
                content = epub.read(file_path).decode('utf-8')
                text = extract_text_from_html(content)

                if len(text.strip()) > 100:
                    chapter_num += 1
                    title = f"Chapter {chapter_num}"

                    title_match = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', content, re.IGNORECASE)
                    if title_match:
                        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

                    chapters.append((title, text))
            except (KeyError, UnicodeDecodeError):
                continue

    return chapters


def epub_to_txt(epub_path: str, output_path: str = None) -> str:
    """Convert EPUB to TXT with chapter markers."""
    if not output_path:
        output_path = str(Path(epub_path).with_suffix('.txt'))

    chapters = get_epub_chapters(epub_path)

    if not chapters:
        print("Error: No chapters found in EPUB", file=sys.stderr)
        sys.exit(1)

    with open(output_path, 'w', encoding='utf-8') as f:
        for i, (title, text) in enumerate(chapters):
            if i > 0:
                f.write('\n\n')
            # Use numeric chapter marker compatible with detect-chapters.py
            f.write(f"第{i + 1}章 {title}\n")
            f.write(text)

    print(f"Extracted {len(chapters)} chapters to {output_path}")
    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: epub2txt.py <input.epub> [output.txt]", file=sys.stderr)
        sys.exit(1)

    epub_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    epub_to_txt(epub_path, output_path)


if __name__ == '__main__':
    main()
