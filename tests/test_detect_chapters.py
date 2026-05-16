"""Tests for detect-chapters.py"""

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).parent.parent / 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

spec = importlib.util.spec_from_file_location("detect_chapters", f"{SCRIPTS_DIR}/detect-chapters.py")
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
detect_chapters = _mod.detect_chapters
is_volume_marker = _mod.is_volume_marker

TEST_DIR = Path(__file__).parent / 'fixtures'


def setup_module():
    TEST_DIR.mkdir(exist_ok=True)


def _write_fixture(name: str, content: str) -> str:
    p = TEST_DIR / name
    p.write_text(content, encoding='utf-8')
    return str(p)


def test_chinese_chapters():
    path = _write_fixture('chinese.txt', '第一章 开始\n内容\n第二章 发展\n内容\n第三章 结局\n内容')
    chapters = detect_chapters(path)
    assert len(chapters) == 3
    assert chapters[0]['title'] == '第一章 开始'
    assert chapters[0]['start_line'] == 1
    assert chapters[1]['start_line'] == 3
    assert chapters[2]['end_line'] == 6


def test_english_chapters():
    path = _write_fixture('english.txt', 'Chapter 1 Start\nContent\nChapter 2 Middle\nContent')
    chapters = detect_chapters(path)
    assert len(chapters) == 2
    assert chapters[0]['title'] == 'Chapter 1 Start'


def test_no_markers():
    path = _write_fixture('nomarkers.txt', 'Some text\nMore text\nEven more')
    chapters = detect_chapters(path)
    assert len(chapters) == 1
    assert chapters[0]['id'] == 1
    assert chapters[0]['end_line'] == 3


def test_volume_markers_excluded():
    path = _write_fixture('volumes.txt', '第一卷 大纲\n卷内容\n第一章 正文\n内容\n第二章 内容\n内容')
    chapters = detect_chapters(path)
    assert len(chapters) == 2
    assert '第一章' in chapters[0]['title']


def test_mixed_formats():
    path = _write_fixture('mixed.txt', '## Prologue\nContent\n第一章 开始\nContent\nChapter 3 End\nContent')
    chapters = detect_chapters(path)
    assert len(chapters) == 3


def test_empty_file():
    path = _write_fixture('empty.txt', '')
    chapters = detect_chapters(path)
    assert len(chapters) == 0


def test_is_volume_marker():
    assert is_volume_marker('第一卷 大纲')
    assert is_volume_marker('Volume 1')
    assert not is_volume_marker('第一章 正文')
