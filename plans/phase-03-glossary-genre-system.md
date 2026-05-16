---
phase: 3
title: "Glossary & Genre System"
status: pending
priority: P1
effort: "3h"
dependencies: [1]
---

# Phase 3: Glossary & Genre System

## Overview

Create the 2-tier glossary system (default + genre) with deep-merge logic, 7 genre profiles with pronoun sets, and the glossary loader script. Glossary is treated as HINT, not hard rules — AI decides contextually.

## Requirements

- Functional: 7 genres supported, glossary terms merged correctly, AI receives glossary hints
- Non-functional: Glossary loads in <1s, deep-merge handles all edge cases, genre auto-detection works

## Architecture

```
glossary/
├── default.json               ← Tier 1: Universal terms (all genres)
└── genres/                    ← Tier 2: Genre-specific overrides
    ├── tienxia.json           ← Tiên Hiệp (Cultivation)
    ├── wuxia.json             ← Kiếm Hiệp (Martial Arts)
    ├── urban.json             ← Thành Thị (Urban Fantasy)
    ├── historical.json        ← Lịch Sử (Historical)
    ├── gamelit.json           ← GameLit (Game Systems)
    ├── horror.json            ← Kinh Dị (Horror)
    └── fantasy.json           ← Fantasy (Generic)

scripts/
└── glossary-loader.py         ← 2-tier deep-merge + genre detection

Cascade (lower → higher priority):
  Tier 1: default.json (base rules, safe for all genres)
  Tier 2: genres/<genre>.json (genre-specific overrides)
```

### Glossary JSON Schema

```json
{
  "version": 1,
  "genre": "tienxia",
  "terms": {
    "修炼": "tu luyện",
    "境界": "cảnh giới",
    "金丹": "Kim Đan",
    "元婴": "Nguyên Anh"
  },
  "characters": {
    "林凡": "Lâm Phàm",
    "苏雪": "Tô Tuyết"
  },
  "protected_phrases": [
    "青云宗",
    "天剑门"
  ],
  "compound_context": {
    "prefixes": ["大", "小", "老", "少"],
    "suffixes": ["哥", "姐", "弟", "妹", "兄", "弟"]
  },
  "pronoun_rules": [
    {"from": "他", "to": "hắn", "context": "narrative_male_3rd"},
    {"from": "她", "to": "nàng", "context": "narrative_female_3rd"}
  ],
  "notes": "Genre-specific terms for cultivation novels"
}
```

### Deep-Merge Logic (from proofreader's apply_glossary.py)

When merging Tier 1 + Tier 2:
- **terms**: Tier 2 overrides Tier 1 (same key → Tier 2 wins)
- **characters**: Tier 2 overrides Tier 1
- **protected_phrases**: APPEND (both preserved, no duplicates)
- **compound_context**: Merge prefixes/suffixes arrays (union)
- **pronoun_rules**: Merge by `from` key (same `from` → Tier 2 wins)

### Glossary-as-Hint Philosophy

From proofreader's chunk_translate.py:
> "Glossary và examples là HINT, AI tự đọc ngữ cảnh để phán đoán."

Translation: Glossary is a HINT, AI reads context to decide. Not hard rules.

This means:
- AI can override glossary terms when context demands it
- AI should explain overrides in translation notes
- Glossary provides starting point, not absolute constraint

## Related Code Files

- Create: `glossary/default.json`
- Create: `glossary/genres/tienxia.json`
- Create: `glossary/genres/wuxia.json`
- Create: `glossary/genres/urban.json`
- Create: `glossary/genres/historical.json`
- Create: `glossary/genres/gamelit.json`
- Create: `glossary/genres/horror.json`
- Create: `glossary/genres/fantasy.json`
- Create: `scripts/glossary-loader.py`

## Implementation Steps

### 3.1 Create glossary/default.json

Universal terms safe for all genres:
```json
{
  "version": 1,
  "genre": "default",
  "terms": {
    "你好": "xin chào",
    "谢谢": "cảm ơn",
    "对不起": "xin lỗi",
    "师父": "sư phụ",
    "师兄": "sư huynh",
    "师姐": "sư tỷ",
    "弟子": "đệ tử",
    "长老": "trưởng lão",
    "掌门": "chưởng môn",
    "宗门": "tông môn"
  },
  "characters": {},
  "protected_phrases": [],
  "compound_context": {
    "prefixes": ["大", "小", "老", "少"],
    "suffixes": ["哥", "姐", "弟", "妹", "兄", "弟"]
  },
  "pronoun_rules": [
    {"from": "他", "to": "hắn", "context": "narrative_male_3rd"},
    {"from": "她", "to": "nàng", "context": "narrative_female_3rd"},
    {"from": "我", "to": "ta", "context": "narrative_1st"},
    {"from": "你", "to": "ngươi", "context": "dialogue_2nd_formal"}
  ],
  "notes": "Universal terms for Chinese web novels"
}
```

### 3.2 Create 7 Genre Profiles

Each genre profile overrides/adds genre-specific terms:

**tienxia.json** — Tiên Hiệp (Cultivation)
- Terms: tu luyện, cảnh giới, Kim Đan, Nguyên Anh, Hóa Thần, Đại Thừa
- Tone: Formal, ancient, spiritual
- Pronouns: hắn/y (male), nàng (female)

**wuxia.json** — Kiếm Hiệp (Martial Arts)
- Terms: kiếm pháp, quyền pháp, nội công, khinh công
- Tone: Action-packed, honor-focused
- Pronouns: y (male), nàng (female)

**urban.json** — Thành Thị (Urban Fantasy)
- Terms: xe, điện thoại, tòa nhà, công ty
- Tone: Modern, casual, dialogue-heavy
- Pronouns: anh (male), cô ấy (female)

**historical.json** — Lịch Sử (Historical)
- Terms: hoàng đế, thái tử, hoàng hậu, ngự sử
- Tone: Formal, period-accurate
- Pronouns: hắn (male), nàng (female)

**gamelit.json** — GameLit (Game Systems)
- Terms: Level, exp, skill tree, HP, MP
- Tone: Technical, progression-focused
- Pronouns: hắn (male), nàng (female)

**horror.json** — Kinh Dị (Horror)
- Terms: ma, quỷ, oan hồn, âm khí
- Tone: Dark, eerie, atmosphere-driven
- Pronouns: hắn (male), nàng (female)

**fantasy.json** — Fantasy (Generic)
- Terms: phép thuật, pháp sư, rồng, elf
- Tone: Epic, diverse
- Pronouns: hắn (male), nàng (female)

### 3.3 Create scripts/glossary-loader.py

```python
#!/usr/bin/env python3
"""Glossary loader with 2-tier deep-merge and genre detection."""

import json
import sys
from pathlib import Path
from typing import Any

def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge glossary: override wins for terms/characters, append for protected_phrases."""
    result = base.copy()
    
    for key, value in override.items():
        if key in result:
            if key == 'terms' or key == 'characters':
                # Override wins
                result[key] = {**result[key], **value}
            elif key == 'protected_phrases':
                # Append, no duplicates
                result[key] = list(set(result[key] + value))
            elif key == 'compound_context':
                # Merge arrays (union)
                result[key] = {
                    'prefixes': list(set(result[key].get('prefixes', []) + value.get('prefixes', []))),
                    'suffixes': list(set(result[key].get('suffixes', []) + value.get('suffixes', [])))
                }
            elif key == 'pronoun_rules':
                # Merge by 'from' key
                by_from = {r['from']: r for r in result[key]}
                for rule in value:
                    by_from[rule['from']] = rule
                result[key] = list(by_from.values())
            else:
                result[key] = value
        else:
            result[key] = value
    
    return result

def load_glossary(genre: str, glossary_dir: Path) -> dict:
    """Load and merge glossary: default.json + genres/<genre>.json."""
    default_path = glossary_dir / 'default.json'
    genre_path = glossary_dir / 'genres' / f'{genre}.json'
    
    if not default_path.exists():
        print(f"Error: Default glossary not found at {default_path}", file=sys.stderr)
        sys.exit(1)
    
    base = load_json(default_path)
    
    if genre_path.exists():
        override = load_json(genre_path)
        return deep_merge(base, override)
    
    return base

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
        return 'fantasy'  # Default fallback
    
    return max(scores, key=scores.get)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: glossary-loader.py <genre> [glossary_dir]")
        sys.exit(1)
    
    genre = sys.argv[1]
    glossary_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('glossary')
    
    glossary = load_glossary(genre, glossary_dir)
    print(json.dumps(glossary, ensure_ascii=False, indent=2))
```

### 3.4 Integrate with translate.toml

In the TOML command, use `!{shell}` to load glossary:
```
!{python3 scripts/glossary-loader.py {{genre}} glossary}
```

Or use `read_file` to load the merged JSON directly.

## Success Criteria

- [ ] `default.json` contains universal terms for all genres
- [ ] 7 genre profiles created with genre-specific terms
- [ ] Deep-merge correctly handles: terms override, protected_phrases append, compound_context union, pronoun_rules merge by `from`
- [ ] `glossary-loader.py` loads and merges glossary correctly
- [ ] Genre auto-detection works from 5KB text sample
- [ ] Glossary loaded via `read_file` or `!{shell}` in translate.toml
- [ ] AI receives glossary as HINT, not hard rule

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Glossary too large for context | MEDIUM | Keep under 500 terms, most-used only |
| Deep-merge edge cases | MEDIUM | Test with conflicting terms across tiers |
| Genre detection wrong | MEDIUM | Allow `--genre` override, detection is optional |
| Protected phrases conflict | LOW | Union merge preserves both |

## Security Considerations

- Glossary files are read-only
- No user input in shell commands
- Genre detection is local-only

## Next Steps

- Phase 4 depends on this: Translation engine uses glossary hints
- Phase 5 depends on this: Validation checks glossary consistency
