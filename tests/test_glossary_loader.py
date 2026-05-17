"""Tests for glossary-loader.py"""

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).parent.parent / 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

spec = importlib.util.spec_from_file_location("glossary_loader", f"{SCRIPTS_DIR}/glossary-loader.py")
if spec is None or spec.loader is None:
    raise ImportError(f"Could not load glossary-loader.py")
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
deep_merge = _mod.deep_merge
load_glossary = _mod.load_glossary
detect_genre = _mod.detect_genre

GLOSSARY_DIR = Path(__file__).parent.parent / 'glossary'


def test_deep_merge_terms_override():
    base = {'terms': {'a': '1', 'b': '2'}}
    override = {'terms': {'b': '3', 'c': '4'}}
    result = deep_merge(base, override)
    assert result['terms'] == {'a': '1', 'b': '3', 'c': '4'}


def test_deep_merge_protected_phrases_append():
    base = {'protected_phrases': ['a', 'b']}
    override = {'protected_phrases': ['b', 'c']}
    result = deep_merge(base, override)
    assert set(result['protected_phrases']) == {'a', 'b', 'c'}


def test_deep_merge_compound_context_union():
    base = {'compound_context': {'prefixes': ['大'], 'suffixes': ['哥']}}
    override = {'compound_context': {'prefixes': ['小'], 'suffixes': ['姐']}}
    result = deep_merge(base, override)
    assert set(result['compound_context']['prefixes']) == {'大', '小'}
    assert set(result['compound_context']['suffixes']) == {'哥', '姐'}


def test_deep_merge_pronoun_rules_by_from():
    base = {'pronoun_rules': [{'from': '他', 'to': 'hắn'}]}
    override = {'pronoun_rules': [{'from': '他', 'to': 'y'}, {'from': '她', 'to': 'nàng'}]}
    result = deep_merge(base, override)
    by_from = {r['from']: r['to'] for r in result['pronoun_rules']}
    assert by_from['他'] == 'y'
    assert by_from['她'] == 'nàng'


def test_load_glossary_default():
    glossary = load_glossary('nonexistent', GLOSSARY_DIR)
    assert 'terms' in glossary
    assert '你好' in glossary['terms']


def test_load_glossary_with_genre():
    glossary = load_glossary('tienxia', GLOSSARY_DIR)
    assert 'tu luyện' in glossary['terms'].values() or '修炼' in glossary['terms']


def test_detect_genre_tienxia():
    text = '他开始修炼，境界不断提升，终于凝结金丹'
    assert detect_genre(text) == 'tienxia'


def test_detect_genre_wuxia():
    text = '他练成了绝世剑法，内功深厚，轻功了得'
    assert detect_genre(text) == 'wuxia'


def test_detect_genre_urban():
    text = '他在城市里的公司上班，用手机联系同事'
    assert detect_genre(text) == 'urban'


def test_detect_genre_fallback():
    text = '一些没有关键词的普通文本'
    assert detect_genre(text) == 'fantasy'
