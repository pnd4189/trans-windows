"""Tests for epub2txt.py"""

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).parent.parent / 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

spec = importlib.util.spec_from_file_location("epub2txt", f"{SCRIPTS_DIR}/epub2txt.py")
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
extract_text_from_html = _mod.extract_text_from_html
HTMLTextExtractor = _mod.HTMLTextExtractor


def test_extract_simple_html():
    html = '<p>Hello</p><p>World</p>'
    text = extract_text_from_html(html)
    assert 'Hello' in text
    assert 'World' in text


def test_extract_removes_scripts():
    html = '<p>Keep</p><script>var x = 1;</script><p>This too</p>'
    text = extract_text_from_html(html)
    assert 'var x' not in text
    assert 'Keep' in text
    assert 'This too' in text


def test_extract_removes_styles():
    html = '<p>Text</p><style>.cls{color:red}</style><p>More</p>'
    text = extract_text_from_html(html)
    assert 'color:red' not in text
    assert 'Text' in text


def test_extract_headings():
    html = '<h1>Title</h1><p>Content</p>'
    text = extract_text_from_html(html)
    assert 'Title' in text


def test_extract_nested_html():
    html = '<div><p>Outer <b>bold</b> text</p></div>'
    text = extract_text_from_html(html)
    assert 'bold' in text
    assert 'Outer' in text


def test_extract_chinese_html():
    html = '<p>第一章 开始</p><p>这是内容</p>'
    text = extract_text_from_html(html)
    assert '第一章' in text
    assert '这是内容' in text
