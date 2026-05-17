#!/usr/bin/env python3
"""EPUB to TXT converter with chapter structure preservation."""

import re
import sys
import zipfile
import xml.etree.ElementTree as ET
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
        ns = {'opf': 'http://www.idpf.org/2007/opf'}

        try:
            root = ET.fromstring(opf_content)
        except ET.ParseError as e:
            print(f"Error: Invalid OPF XML: {e}", file=sys.stderr)
            return []

        # Extract manifest items via XML
        manifest: dict[str, str] = {}
        for item in root.findall('.//opf:manifest/opf:item', ns):
            item_id = item.get('id')
            href = item.get('href')
            if item_id and href:
                manifest[item_id] = href

        # Extract spine order via XML
        spine_items = [ref.get('idref') for ref in root.findall('.//opf:spine/opf:itemref', ns)]

        base_path = str(Path(opf_path).parent)
        chapter_num = 0

        for item_id in spine_items:
            if not item_id or item_id not in manifest:
                continue

            href = manifest[item_id]
            # Fix zip path traversal: sanitize href and ensure it stays within base_path
            normalized_href = str(Path(href).resolve().relative_to(Path(href).resolve().anchor))
            file_path = f"{base_path}/{normalized_href}" if base_path else normalized_href
            
            # Additional safety check
            if '..' in normalized_href or normalized_href.startswith('/'):
                 continue

            try:
                # Zip bomb protection: check size before reading
                info = epub.getinfo(file_path)
                if info.file_size > 10 * 1024 * 1024: # 10MB limit per file
                    print(f"Warning: Skipping large file {file_path} ({info.file_size} bytes)", file=sys.stderr)
                    continue
                
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
