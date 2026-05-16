---
phase: 6
title: "EPUB Support"
status: pending
priority: P3
effort: "2h"
dependencies: [1]
---

# Phase 6: EPUB Support

## Overview

Add EPUB file support: extract text from EPUB files while preserving chapter structure from the EPUB TOC (Table of Contents). This is optional — TXT input works without this phase.

## Requirements

- Functional: Extract text from EPUB, preserve chapter structure, convert to TXT
- Non-functional: Handle large EPUBs (500+ pages), preserve encoding

## Architecture

```
scripts/
└── epub2txt.py                ← EPUB extraction script

Flow:
1. User provides .epub file
2. epub2txt.py extracts text from all chapters
3. Preserves chapter structure from EPUB TOC
4. Outputs single .txt file with chapter markers
5. Feed into normal translation pipeline
```

## Related Code Files

- Create: `scripts/epub2txt.py`

## Implementation Steps

### 6.1 Create scripts/epub2txt.py

```python
#!/usr/bin/env python3
"""EPUB to TXT converter with chapter structure preservation."""

import sys
import zipfile
import re
from pathlib import Path
from typing import List, Tuple
from html.parser import HTMLParser

class HTMLTextExtractor(HTMLParser):
    """Extract text from HTML content."""
    
    def __init__(self):
        super().__init__()
        self.text = []
        self._in_tag = False
    
    def handle_starttag(self, tag: str, attrs: list):
        if tag in ('script', 'style'):
            self._in_tag = True
    
    def handle_endtag(self, tag: str):
        if tag in ('script', 'style'):
            self._in_tag = False
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text.append('\n')
    
    def handle_data(self, data: str):
        if not self._in_tag:
            self.text.append(data)
    
    def get_text(self) -> str:
        return ''.join(self.text)

def extract_text_from_html(html_content: str) -> str:
    """Extract plain text from HTML."""
    extractor = HTMLTextExtractor()
    extractor.feed(html_content)
    text = extractor.get_text()
    # Clean up whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def get_epub_chapters(epub_path: str) -> List[Tuple[str, str]]:
    """Extract chapters from EPUB file.
    
    Returns list of (chapter_title, chapter_text) tuples.
    """
    chapters = []
    
    with zipfile.ZipFile(epub_path, 'r') as epub:
        # Find content.opf to get chapter order
        opf_path = None
        for name in epub.namelist():
            if name.endswith('.opf'):
                opf_path = name
                break
        
        if not opf_path:
            print("Error: No OPF file found in EPUB", file=sys.stderr)
            return []
        
        # Parse OPF to get spine (reading order)
        opf_content = epub.read(opf_path).decode('utf-8')
        
        # Extract manifest items
        manifest = {}
        for match in re.finditer(r'<item\s+id="([^"]+)"\s+href="([^"]+)"', opf_content):
            item_id, href = match.groups()
            manifest[item_id] = href
        
        # Extract spine order
        spine_items = re.findall(r'<itemref\s+idref="([^"]+)"', opf_content)
        
        # Extract text from each spine item
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
                
                if len(text.strip()) > 100:  # Skip very short content
                    chapter_num += 1
                    title = f"Chapter {chapter_num}"
                    
                    # Try to extract title from HTML
                    title_match = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', content, re.IGNORECASE)
                    if title_match:
                        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                    
                    chapters.append((title, text))
            except (KeyError, UnicodeDecodeError):
                continue
    
    return chapters

def epub_to_txt(epub_path: str, output_path: str = None) -> str:
    """Convert EPUB to TXT file.
    
    Args:
        epub_path: Path to EPUB file
        output_path: Path for output TXT file (optional)
    
    Returns:
        Path to output file
    """
    if not output_path:
        output_path = Path(epub_path).with_suffix('.txt')
    
    chapters = get_epub_chapters(epub_path)
    
    if not chapters:
        print("Error: No chapters found in EPUB", file=sys.stderr)
        sys.exit(1)
    
    # Write to TXT with chapter markers
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, (title, text) in enumerate(chapters):
            if i > 0:
                f.write('\n\n')
            f.write(f"第{title}章\n")
            f.write(text)
    
    print(f"Extracted {len(chapters)} chapters to {output_path}")
    return str(output_path)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: epub2txt.py <input.epub> [output.txt]")
        sys.exit(1)
    
    epub_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    epub_to_txt(epub_path, output_path)
```

### 6.2 Chapter Marker Format

The output uses Chinese chapter markers (`第X章`) that `detect-chapters.py` can parse:
```
第Chapter 1章
[chapter text]

第Chapter 2章
[chapter text]
```

### 6.3 Integration with /translate

When user provides EPUB:
1. Run `epub2txt.py novel.epub novel.txt`
2. Run normal translation pipeline on `novel.txt`
3. Chapter detection from EPUB TOC is more reliable than regex

## Success Criteria

- [ ] `epub2txt.py` extracts text from EPUB files
- [ ] Chapter structure preserved from EPUB TOC
- [ ] Output uses `第X章` markers compatible with `detect-chapters.py`
- [ ] Large EPUBs (500+ pages) handled without errors
- [ ] Unicode encoding preserved (Chinese characters intact)
- [ ] Script/Skip content (CSS, JS) excluded from output

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| EPUB structure varies widely | MEDIUM | Fallback: treat entire content as single chapter |
| Chapter titles not in TOC | LOW | Use generic "Chapter N" titles |
| Large EPUBs cause memory issues | LOW | Stream processing, don't load all at once |
| DRM-protected EPUBs | HIGH | Cannot handle — report error to user |

## Security Considerations

- EPUB is a ZIP file — handle zip bombs gracefully
- No code execution from EPUB content
- HTML parsing ignores script/style tags

## Next Steps

- This phase is independent — can be done anytime after Phase 1
- Output feeds into normal translation pipeline
