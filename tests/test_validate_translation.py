"""Tests for validate-translation.py"""

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).parent.parent / 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

spec = importlib.util.spec_from_file_location("validate_translation", f"{SCRIPTS_DIR}/validate-translation.py")
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
count_chinese_chars = _mod.count_chinese_chars
count_paragraphs = _mod.count_paragraphs
check_chinese_residual = _mod.check_chinese_residual
check_paragraph_count = _mod.check_paragraph_count
check_length_ratio = _mod.check_length_ratio
check_pronoun_leakage = _mod.check_pronoun_leakage


def test_count_chinese_chars():
    assert count_chinese_chars('你好世界') == 4
    assert count_chinese_chars('Hello') == 0
    assert count_chinese_chars('Hello你好') == 2


def test_count_paragraphs():
    assert count_paragraphs('line1\nline2\nline3') == 3
    assert count_paragraphs('line1\n\nline2') == 2
    assert count_paragraphs('') == 0


def test_chinese_residual_clean():
    errors = check_chinese_residual('Đây là bản dịch tiếng Việt')
    assert len(errors) == 0


def test_chinese_residual_found():
    errors = check_chinese_residual('Dịch từ 你好 sang xin chào')
    assert len(errors) > 0
    assert 'Chinese' in errors[0]


def test_paragraph_count_pass():
    errors = check_paragraph_count('a\nb\nc', 'x\ny\nz')
    assert len(errors) == 0


def test_paragraph_count_fail():
    errors = check_paragraph_count('a\nb\nc', 'x')
    assert len(errors) > 0


def test_length_ratio_normal():
    errors = check_length_ratio('abcde', 'abcde')
    assert len(errors) == 0


def test_length_ratio_too_short():
    errors = check_length_ratio('a' * 100, 'b')
    assert len(errors) > 0
    assert 'short' in errors[0].lower()


def test_length_ratio_too_long():
    errors = check_length_ratio('a', 'b' * 300)
    assert len(errors) > 0
    assert 'long' in errors[0].lower()


def test_pronoun_leakage_clean():
    errors = check_pronoun_leakage('Hắn nói với đối phương')
    assert len(errors) == 0


def test_pronoun_leakage_found():
    errors = check_pronoun_leakage('Hắn nhìn ngươi và nói')
    assert len(errors) > 0


def test_pronoun_leakage_in_dialogue_ok():
    errors = check_pronoun_leakage('Hắn nói: "Ngươi muốn chết!"')
    assert len(errors) == 0
