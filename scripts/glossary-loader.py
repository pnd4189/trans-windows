#!/usr/bin/env python3
"""Glossary loader with 3-tier deep-merge (default + genre + per-novel)."""

import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge: override wins for terms/characters, append for protected_phrases."""
    result = base.copy()

    for key, value in override.items():
        if key in result:
            if key in ('terms', 'characters'):
                result[key] = {**result[key], **value}
            elif key == 'protected_phrases':
                result[key] = list(set(result[key] + value))
            elif key == 'compound_context':
                result[key] = {
                    'prefixes': list(set(result[key].get('prefixes', []) + value.get('prefixes', []))),
                    'suffixes': list(set(result[key].get('suffixes', []) + value.get('suffixes', [])))
                }
            elif key == 'pronoun_rules':
                by_from = {r['from']: r for r in result[key]}
                for rule in value:
                    by_from[rule['from']] = rule
                result[key] = list(by_from.values())
            else:
                result[key] = value
        else:
            result[key] = value

    return result


def load_glossary(genre: str, glossary_dir: Path = Path('glossary'),
                  novel_glossary: Path | None = None) -> dict:
    """3-tier merge: default.json + genres/<genre>.json + novel-glossary.json.

    The novel-tier (accumulated AI-extracted entities) has highest precedence
    so first-seen character/place/term names stay consistent across chapters.
    """
    default_path = glossary_dir / 'default.json'
    genre_path = glossary_dir / 'genres' / f'{genre}.json'

    if not default_path.exists():
        print(f"Error: Default glossary not found at {default_path}", file=sys.stderr)
        sys.exit(1)

    merged = load_json(default_path)

    if genre_path.exists():
        merged = deep_merge(merged, load_json(genre_path))

    if novel_glossary and novel_glossary.exists():
        try:
            merged = deep_merge(merged, load_json(novel_glossary))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: could not load novel glossary {novel_glossary}: {e}", file=sys.stderr)

    return merged


def detect_genre(text_sample: str) -> str:
    """Detect genre from text sample using keyword heuristics."""
    genre_keywords = {
        'tienxia': ['修炼', '境界', '金丹', '元婴', '化神', '大乘', '仙', '道'],
        'wuxia': ['剑法', '拳法', '内功', '轻功', '江湖', '武林', '侠'],
        'urban': ['手机', '公司', '大学', '城市', '现代', '都市'],
        'historical': ['皇帝', '太子', '皇后', '朝廷', '大臣', '王朝'],
        'gamelit': ['等级', '经验', '技能', '属性', '装备', '副本'],
        'horror': ['鬼', '魂', '灵异', '恐怖', '阴', '邪'],
        'fantasy': ['魔法', '法师', '龙', '精灵', '王国', '冒险']
    }

    scores = {}
    for genre, keywords in genre_keywords.items():
        scores[genre] = sum(1 for kw in keywords if kw in text_sample)

    if max(scores.values()) == 0:
        return 'fantasy'

    return max(scores, key=lambda k: scores[k])


def main():
    if len(sys.argv) < 2:
        print("Usage: glossary-loader.py <genre> [glossary_dir] [novel_glossary_path]", file=sys.stderr)
        sys.exit(1)

    genre = sys.argv[1]
    glossary_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('glossary')
    novel_glossary = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    glossary = load_glossary(genre, glossary_dir, novel_glossary)
    print(json.dumps(glossary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
