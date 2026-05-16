# Brainstorm: Gemini CLI Chinese-to-Vietnamese Novel Translator

**Date:** 2026-05-16
**Status:** Final Proposal

---

## Problem Statement

Build a Gemini CLI extension with MCP server that translates Chinese web novels to Vietnamese. Uses Gemini CLI's built-in model (no API key). Supports TXT + EPUB input, bilingual output option, intelligent chapter detection, context-aware translation with flexible glossary.

---

## Research Summary

### Gemini CLI
- Custom commands: TOML in `~/.gemini/commands/` or `.gemini/commands/`
- Extensions: `gemini-extension.json` manifest + `commands/`, `skills/`, MCP servers
- Template vars: `{{args}}`, `!{shell}`, `@{file}` — no `{{model}}` var
- Quotas (Ultra): 2,000 req/day, no published RPM/RPS, 1M context window

### MCP Server Patterns
- DeepL MCP: 9 translation tools, stateless, Zod schemas
- Readwise MCP: chunking with `contentMaxLength` + `start_index`, rate limiting with retry-after
- gemini-mcp-tool: wraps Gemini CLI as MCP tool, 2.2k stars
- Official SDK: `@modelcontextprotocol/server`, stdio transport, Zod v4 validation
- FastMCP: higher-level abstraction with streaming + progress reporting

### Vietnamese Translation (from chinese-novel-proofreader v3.3)
- 7 genre profiles with distinct pronoun sets
- 27 verified real-world error cases
- Compound noun protection (16+ bạn+X variants)
- Narrative vs dialogue pronoun distinction (#1 MT error source)
- Han-Viet density varies by genre (HIGH for tienxia, LOW for urban)

---

## Final Design

### Architecture: Gemini CLI Extension + MCP Server

```
User: /translate novel.txt --genre tienxia --bilingual
        │
        ▼
  TOML Command (commands/translate.toml)
    → Injects file via @{args}
    → Sends to Gemini model with translation instructions
        │
        ▼
  Gemini Model (1 session, 1M context)
    → Calls MCP tool: detect_chapters(file_path)
    → Calls MCP tool: get_glossary(genre)
    → Calls MCP tool: get_genre_guide(genre)
    → Translates each chapter (model sees full context)
    → Calls MCP tool: save_translation(output_path, text)
    → Calls MCP tool: validate_translation(original, translated)
        │
        ▼
  Output: translated_novel.txt (or bilingual_novel.txt)
```

**Key insight:** MCP server handles deterministic logic (file I/O, chapter detection, glossary loading, caching, validation). Gemini model handles translation decisions with full context. Model is NOT constrained by rigid rules — it receives guidelines and adapts based on context.

### Project Structure

```
cli-translator/
├── gemini-extension.json          # Extension manifest
├── package.json                   # Node.js deps
├── tsconfig.json                  # TypeScript config
├── src/
│   ├── index.ts                   # MCP server entry point
│   ├── tools/
│   │   ├── detect-chapters.ts     # Chapter pattern detection
│   │   ├── get-glossary.ts        # Load & merge glossary cascade
│   │   ├── get-genre-guide.ts     # Load genre tone guide
│   │   ├── save-translation.ts    # Write output file
│   │   ├── validate-translation.ts # Paragraph count, length ratio, CJK residual
│   │   └── get-cache.ts           # Check/load cached translations
│   ├── services/
│   │   ├── chapter-detector.ts    # Regex patterns + scoring
│   │   ├── glossary-manager.ts    # 4-tier cascade merge
│   │   ├── genre-detector.ts      # Keyword scoring for 7 genres
│   │   ├── epub-reader.ts         # EPUB extraction (epubjs)
│   │   ├── cache-manager.ts       # SHA-256 content-addressed cache
│   │   └── rate-limiter.ts        # Token bucket + exponential backoff
│   ├── types/
│   │   └── index.ts               # Shared types
│   └── lib/
│       ├── config.ts              # Environment/config
│       └── logger.ts              # Logging
├── commands/
│   └── translate.toml             # Slash command definition
├── skills/
│   └── novel-translator/
│       └── SKILL.md               # Translation expertise (auto-activated)
├── glossary/
│   ├── default.json               # Tier 1: universal terms
│   └── genres/
│       ├── tienxia.json           # Tier 2: xianxia profile
│       ├── wuxia.json             # Tier 2: martial arts
│       ├── urban.json             # Tier 2: modern
│       ├── historical.json        # Tier 2: palace
│       ├── gamelit.json           # Tier 2: game lit
│       ├── horror.json            # Tier 2: horror
│       └── fantasy.json           # Tier 2: fantasy
├── references/
│   ├── translation-principles.md  # P1-P10 flexible guidelines
│   ├── pronoun-guide.md           # Genre-specific pronoun reference
│   └── common-errors.md           # 27 verified error cases
├── GEMINI.md                      # Extension context
└── README.md
```

### MCP Tools Design

#### Tool 1: `detect-chapters`
```typescript
// Input
{ file_path: string }
// Output
{
  chapters: [
    { index: number, title: string, start_line: number, end_line: number }
  ],
  pattern_detected: string,  // e.g., "第X章", "Chương X"
  total_chapters: number
}
```

#### Tool 2: `get-chapter`
```typescript
// Input
{ file_path: string, chapter_index: number }
// Output
{
  title: string,
  text: string,           // Full chapter text
  char_count: number,
  context_before: string, // Last 300 chars of previous chapter
  context_after: string   // First 300 chars of next chapter
}
```

#### Tool 3: `get-glossary`
```typescript
// Input
{ genre: string, novel_dir?: string }
// Output
{
  terms: Record<string, string>,          // Chinese → Vietnamese
  characters: Record<string, Character>,  // Name, gender, pronoun
  pronoun_rules: PronounRule[],
  protected_phrases: string[],            // Compound nouns
  genre_notes: string                     // Genre-specific guidance
}
```

#### Tool 4: `get-genre-guide`
```typescript
// Input
{ genre: string }
// Output
{
  register: string,           // "Cổ trang, Hán-Việt cao"
  pronoun_set: object,        // Narrative + dialogue pronouns
  vocab_preferences: object,  // Preferred vs avoided terms
  anti_modernism_block: string[],
  examples: BeforeAfter[]     // 5-6 before/after examples
}
```

#### Tool 5: `save-translation`
```typescript
// Input
{ output_path: string, text: string, chapter_index?: number, bilingual?: boolean }
// Output
{ success: boolean, file_path: string, char_count: number }
```

#### Tool 6: `validate-translation`
```typescript
// Input
{ original: string, translated: string }
// Output
{
  valid: boolean,
  paragraph_count_match: boolean,
  length_ratio: number,        // Should be 0.5-2.0
  cjk_residual: string[],     // Remaining Chinese characters
  issues: string[]             // Any detected problems
}
```

#### Tool 7: `get-translation-cache`
```typescript
// Input
{ chunk_hash: string, glossary_version: string }
// Output
{ cached: boolean, translated?: string }
```

#### Tool 8: `auto-detect-characters`
```typescript
// Input
{ file_path: string }
// Output
{
  characters: [
    {
      name_cn: string,       // Chinese name
      name_vi: string,       // Han-Viet transliteration
      first_appearance: string, // First context where name appears
      frequency: number      // How often the name appears
    }
  ],
  suggested_glossary: Record<string, string>
}
```

#### Tool 9: `get-previous-translation`
```typescript
// Input
{ file_path: string, chapter_index: number }
// Output
{
  previous_translation: string,  // Last chapter's translated text (last 2000 chars)
  character_pronouns: Record<string, string>, // Character → pronoun mapping from previous chapter
  notes: string                  // Any translation notes from previous chapter
}
```

### TOML Command (commands/translate.toml)

```toml
description = "Translate Chinese novel to Vietnamese. Usage: /translate <file> [--genre tienxia] [--bilingual] [--glossary path]"
prompt = """
You are a professional Vietnamese translator specializing in Chinese web novels.

## Your Task
Translate the Chinese novel file to Vietnamese.

## Steps
1. Call `detect-chapters` tool on the file: @{{args}}
2. For each chapter:
   a. Call `get-chapter` to get the full chapter text
   b. Call `get-glossary` with the detected genre
   c. Call `get-genre-guide` for genre-specific guidance
   d. Translate the chapter, following the translation principles below
   e. Call `validate-translation` to check quality
   f. If validation passes, call `save-translation` to write output
3. Report progress after each chapter

## Translation Principles (Flexible — Adapt to Context)
Based on Image #1 guidelines. NOT rigid rules — model adapts to each scene.

### 1. Đại từ xưng hô (Pronouns)
- **ƯU TIÊN** sử dụng "hắn/nàng/người" thay vì đại từ xưng hô thông thường
- Dùng "nữ tử", "nam tử", "lão nhân", "thiếu niên" cho nhân vật (khi phù hợp ngữ cảnh)
- **DUY TRÌ** sự nhất quán tuyệt đối trong cách xưng hô cho MỖI nhân vật trong suốt đoạn
- Phân biệt rõ ràng narrative (ngoài ngoặc kép) vs dialogue (trong ngoặc kép)

### 2. Thuần Việt & Hán-Việt
- **Ưu tiên Thuần Việt:** CHỈ DÙNG từ Hán-Việt khi chúng là thuật ngữ cố định (tên cổ, cách xưng hô đặc biệt: tiền bối, đạo hữu, sư phụ)
- **Hạn chế Hán-Việt:** Không ép Hán-Việt khi từ thuần Việt tự nhiên hơn (ánh mắt > nhãn quan)
- **Thứ tự từ tiếng Việt:** Sửa đổi triệt để để thứ tự danh từ, tính từ, động từ cho phù hợp

### 3. Cấu trúc câu
- **Hoàn toàn tự nhiên:** Viết lại câu sao cho văn bản hoàn toàn tự nhiên bằng tiếng Việt
- **Tách câu phức:** LINH HOẠT chia câu phức đại thành câu đơn/gắn ngắn hơn
- **Dấu phẩy:** ĐẶC BIỆT CHÚ Ý và LOẠI BỎ HOÀN TOÀN việc lạm dụng dấu phẩy
- **Loại bỏ thừa:** Loại bỏ từ thừa và các từ/cụm từ lặp lại không cần thiết

### 4. Diễn đạt, Mạch lạc & Giọng văn
- **Làm rõ nghĩa:** Viết lại các câu văn tối nghĩa, mở cho thật rõ ràng, dễ hiểu
- **Giọng văn:** Duy trì giọng kể nhất quán phù hợp thể loại (cổ trang / hiện đại / võ hiệp...)
- **Khi giữ nguyên:** Giữ nguyên các từ/cụm từ tiếng Việt đã chính xác, không sửa vô lý

## Context
- File: @{{args}}
- Use the MCP tools to get glossary and genre guidance
- If genre is not specified, use `detect-genre` or ask the user
- The glossary provides FLEXIBLE guidance — adapt to context, don't apply mechanically
"""
```

### SKILL.md (skills/novel-translator/SKILL.md)

```yaml
---
name: novel-translator
description: >
  Expertise in translating Chinese web novels to Vietnamese.
  Activate when user asks to "translate", "dịch truyện", "dịch novel",
  or mentions Chinese-to-Vietnamese translation.
---
```

### Glossary Design (Flexible, Temporary Per File)

**Philosophy:** Glossary provides reference material for the model, not hard replacement rules. The model uses its understanding of context to apply terms appropriately.

**Temporary glossary lifecycle:**
1. File translation starts → create temp glossary (Tier 1 default + Tier 2 genre)
2. MCP tool `auto-detect-characters` scans file → adds character names to temp glossary
3. Translation proceeds with temp glossary
4. File translation complete → discard temp glossary
5. No cross-file contamination when translating multiple novels

#### default.json (Tier 1)
```json
{
  "version": "1.0.0",
  "terms": {
    "修炼": "tu luyện",
    "突破": "đột phá",
    "灵气": "linh khí",
    "法宝": "pháp bảo",
    "丹田": "đan điền",
    "金丹": "kim đan",
    "元婴": "nguyên anh",
    "宗门": "tông môn",
    "前辈": "tiền bối",
    "道友": "đạo hữu",
    "师父": "sư phụ"
  },
  "characters": {},
  "protected_phrases": [
    "bạn bè", "bạn học", "bạn thân", "bạn cũ", "bạn đời",
    "anh em", "anh hùng", "anh tài",
    "một mình", "chính mình", "giật mình", "tự mình",
    "nhíu mày", "lông mày", "cau mày"
  ],
  "notes": "These are reference terms. Apply based on context, not mechanically."
}
```

#### genres/tienxia.json (Tier 2)
```json
{
  "inherit": "../default.json",
  "register": "Cổ trang, Hán-Việt cao",
  "pronoun_set": {
    "narrative_male_3rd": "hắn",
    "narrative_female_3rd": "nàng",
    "narrative_1st": "ta",
    "narrative_2nd": "ngươi",
    "elder_male": "lão",
    "elder_female": "bà",
    "negative_male": "gã",
    "negative_female": "ả"
  },
  "terms": {
    "灵气": "linh khí",
    "仙人": "tiên nhân",
    "渡劫": "độ kiếp",
    "化神": "hóa thần",
    "真仙": "chân tiên"
  },
  "anti_modernism_block": [
    "OK", "okay", "wow", "chill", "cool", "bro", "sis",
    "smartphone", "internet", "email", "app", "computer"
  ],
  "notes": "Tiên hiệp register. Use Hán-Việt for cultivation terms. Model should adapt pronouns based on character relationships and context."
}
```

### Rate Limiting Strategy

```typescript
// Token bucket with exponential backoff
class RateLimiter {
  private tokens: number = 20;        // Max 20 requests
  private refillRate: number = 1;     // 1 token per second
  private lastRefill: number = Date.now();

  async acquire(): Promise<void> {
    // Refill tokens
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(20, this.tokens + elapsed * this.refillRate);
    this.lastRefill = now;

    if (this.tokens < 1) {
      const waitMs = ((1 - this.tokens) / this.refillRate) * 1000;
      await new Promise(r => setTimeout(r, waitMs));
      this.tokens = 1;
    }
    this.tokens -= 1;
  }

  async withRetry<T>(fn: () => Promise<T>, maxRetries = 5): Promise<T> {
    for (let i = 0; i < maxRetries; i++) {
      try {
        await this.acquire();
        return await fn();
      } catch (e: any) {
        if (e.status === 429) {
          const delay = Math.pow(2, i) * 5000; // 5s, 10s, 20s, 40s, 80s
          console.log(`Rate limited. Waiting ${delay/1000}s...`);
          await new Promise(r => setTimeout(r, delay));
        } else throw e;
      }
    }
    throw new Error('Max retries exceeded');
  }
}
```

### Chapter Detection

```typescript
const CHAPTER_PATTERNS = [
  { pattern: /第[一二三四五六七八九十百千\d]+[章节回卷]/g, name: 'chinese_chapter' },
  { pattern: /第\s*\d+\s*[章节回卷]/g, name: 'chinese_numbered' },
  { pattern: /[Cc]hương\s*\d+/g, name: 'vietnamese' },
  { pattern: /Chapter\s*\d+/gi, name: 'english' },
  { pattern: /^\d+[\.\s]\s*\S/gm, name: 'numbered' },
];

// Auto-detect: scan first 100 lines, score each pattern, pick winner
function detectPattern(text: string): PatternResult {
  const lines = text.split('\n').slice(0, 100);
  const scores = CHAPTER_PATTERNS.map(p => ({
    ...p,
    score: lines.filter(l => p.pattern.test(l)).length
  }));
  return scores.sort((a, b) => b.score - a.score)[0];
}
```

### EPUB Handling

```typescript
import EPub from 'epub';

async function readEpub(filePath: string): Promise<string> {
  const epub = new EPub(filePath);
  await epub.parse();

  let fullText = '';
  for (const chapter of epub.flow) {
    const html = await epub.getChapter(chapter.id);
    const text = htmlToText(html); // Strip HTML tags
    fullText += text + '\n\n';
  }
  return fullText;
}
```

### Output Modes

**Default (translated only):**
```
translated_novel.txt
├── Chương 1: Title
├── [translated text]
├── Chương 2: Title
├── [translated text]
└── ...
```

**Bilingual (--bilingual flag):**
```
bilingual_novel.txt
├── Chương 1: Title
├── [original Chinese paragraph]
├── [translated Vietnamese paragraph]
├── [original Chinese paragraph]
├── [translated Vietnamese paragraph]
└── ...
```

---

## Comparison: Rigid vs Flexible Glossary

| Aspect | Rigid (chinese-novel-proofreader) | Flexible (Proposed) |
|--------|----------------------------------|---------------------|
| Pronouns | Fixed rules: P1-P10 hard-coded | Guidelines: model adapts to context |
| Terms | Exact replacement: 他→hắn always | Reference: model decides based on scene |
| Compound protection | Regex-based: bạn+X NEVER change | Model awareness: understands compounds |
| Genre register | Block list: OK/wow/chill forbidden | Guidance: model knows register appropriate |
| Quality | Rule-based validation | AI + structural validation |

**Why flexible is better for Gemini CLI:**
- Gemini 2.5 Pro has 1M context — can see full chapter + glossary + guide in one prompt
- Model can understand nuance (e.g., flashback scenes, perspective shifts)
- No false positives from rigid regex (e.g., "OK" in a character's name)
- Model adapts to novel-specific style rather than forcing genre template

---

## Implementation Phases

### Phase 1: Core Extension + MCP Server
- Create `gemini-extension.json` manifest
- Set up TypeScript project with `@modelcontextprotocol/server`
- Implement `detect-chapters` and `get-chapter` tools
- Implement `save-translation` tool
- Implement `auto-detect-characters` tool (scan file for character names)
- Implement `get-previous-translation` tool (chapter context continuity)
- Create `commands/translate.toml` with auto-model detection
- Basic TXT file support

### Phase 2: Glossary & Genre System
- Create `default.json` with universal terms
- Create 7 genre profiles with pronoun sets and vocab
- Implement `get-glossary` tool with temp glossary per file (discarded after)
- Implement `get-genre-guide` tool
- Genre auto-detection via keyword scoring

### Translation Principles & Reference Docs
- Write `references/translation-principles.md` (flexible guidelines from Image #1)
- Write `references/pronoun-guide.md` (genre-specific pronoun reference)
- Write `references/common-errors.md` (27 verified error cases)
- Create `SKILL.md` for auto-activation

### Phase 3: EPUB Support
- Add `epubjs` dependency
- Implement `epub-reader.ts` service
- Handle EPUB → TXT extraction
- Preserve chapter structure from EPUB TOC

### Phase 4: Caching & Rate Limiting
- Implement content-addressed caching (SHA-256)
- Implement rate limiter with exponential backoff (token bucket, 20 req burst, 1/sec refill)
- Add progress display: `Chapter 3/25 [███░░░░░░░] 12% | ETA: 2m`
- Add resume capability (skip cached chapters)
- 2-second delay between chapter requests (configurable)

### Phase 5: Quality Assurance
- Implement `validate-translation` tool
- Paragraph count verification
- Length ratio check (0.5-2.0x)
- Chinese residual detection
- Bilingual output mode (`--bilingual` flag)

### Phase 6: Polish
- Error handling and edge cases
- Logging and debugging
- README documentation
- Testing with sample novels

---

## Resolved Decisions

1. **[Image #1]**: RESOLVED — 4 core principles extracted: pronouns (hắn/nàng priority), Thuần Việt > Hán-Việt, natural sentence restructuring, clarity/mạch lạc.
2. **Glossary auto-learning**: RESOLVED — Auto-detect characters per file, temp glossary discarded after translation.
3. **Previous translation context**: RESOLVED — Chapter N-1's translation (last 2000 chars) + character pronoun mapping passed to chapter N.
4. **Cross-file contamination**: RESOLVED — Temporary glossary per file, no persistence between files.
5. **Model selection**: RESOLVED — Auto-detect active model in Gemini CLI, always use the latest Pro version. MCP tool queries Gemini CLI for current model. User can override with `--model <name>` flag.

## Open Questions

1. **Batch mode**: Should `/translate *.txt` translate all files in a directory? (Low priority — add later)
2. **Chapter splitting output**: Each chapter = 1 file, or all in 1 file? (Default: 1 file, flag --split for separate files)
