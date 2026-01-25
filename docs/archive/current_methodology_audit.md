# Current Methodology Audit

Audit completed: 2026-01-24

## 1. Session Capture Layer

**File:** `ai_logging.zsh`

### Wrapper Functions
```bash
claude()  { _logged_ai claude "$@"; }
ollama()  { _logged_ai ollama "$@"; }
gemini()  { _logged_ai gemini "$@"; }
```

### Capture Mechanism
- Uses `script -q <logfile> <command>` for terminal capture
- Logs to: `~/ai_shell_logs/{app}/{timestamp}.log`
- Timestamp format: `YYYY-MM-DD_HHMMSS`
- Optional `--tag "description"` parameter for session labeling

### Files Created at Session Start
- `.log` - raw script capture (ANSI codes included)
- `.meta` - JSON metadata (app, timestamp, tag, paths)

---

## 2. ANSI Stripping Tools

### Method 1: Perl Regex (`ai_clean` function)
Fast, regex-based stripping:
- CSI sequences: `\e\[[0-9;?]*[a-zA-Z]`
- OSC sequences: `\e\][^\a\e]*(?:\a|\e\\)`
- Character set selection, keypad modes, carriage returns, nulls

### Method 2: Terminal Emulation (`ai_export.py`)
Accurate rendering using `pyte` library:
- Creates virtual terminal (120x50 default)
- Feeds raw log through `pyte.HistoryScreen`
- Renders final output from history + buffer

---

## 3. JSON Conversion (`ai_export.py`)

### Usage
```bash
ai_export <logfile>              # Clean text
ai_export <logfile> --json       # Structured JSON
ai_export <logfile> -o out.json  # Save to file
```

### Current Output Schema
```json
{
  "metadata": {
    "exported_at": "2026-01-22T14:25:42.203664",
    "format_version": "1.0",
    "source_file": "/path/to/logfile"
  },
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "raw_text": "Full rendered terminal output..."
}
```

### Parsing Logic
- Renders log through terminal emulator
- Detects user prompts: lines starting with `❯` or `> `
- Extracts assistant responses as blocks between prompts

---

## 4. Post-Processing Pipeline

### Automatic Trigger (on session close)
```
_postprocess_log <logfile> <cleanfile> <jsonfile> <errorfile>
    │
    ├─ ai_export.py <logfile>           → .txt
    ├─ ai_export.py <logfile> --json    → .json
    │
    ├─ Success: delete .log, keep .txt/.json/.meta
    └─ Failure: write .error, keep .log, notify user
```

---

## 5. Directory Structure

```
~/ai_shell_logs/
├── claude/
│   ├── 2026-01-22_143052.txt    # Clean text
│   ├── 2026-01-22_143052.json   # Structured JSON
│   ├── 2026-01-22_143052.meta   # Metadata + tag
│   └── 2026-01-22_143052.error  # (if processing failed)
├── ollama/
├── gemini/
└── analysis/

~/.claude/projects/               # Claude Code native JSONL
├── {project-path}/
│   ├── sessions-index.json
│   └── {session-id}.jsonl
```

---

## 6. Analysis Tools

| Tool | Purpose |
|------|---------|
| `extract_tool_calls.py` | Tool usage patterns from Claude JSONL |
| `session_forensics.py` | Cross-session pattern analysis |
| `diff_potential.py` | Cache/diff savings analysis |
| `opportunity_study.py` | Optimization opportunity mapping |

---

## 7. Helper Commands

```bash
ai_logs [app]           # List recent logs
ai_tail <app>           # Real-time tail of current session
ai_session              # Show current session path
ai_tags [pattern]       # List/search session tags
ai_tag <log> "tag"      # Add tag retroactively
ai_clean <log>          # Strip ANSI to stdout
```

---

## 8. Gap Analysis vs. Target Spec

Target spec: `session_log_pattern_derived_from_claude.md`

| Feature | Current | Target | Gap |
|---------|---------|--------|-----|
| Session ID | None | Deterministic UUID5 | **Missing** |
| Message ID | None | Deterministic UUID5 | **Missing** |
| Parent chain | None | parentUuid threading | **Missing** |
| Output format | Single `.json` | `.jsonl` (one record/line) | **Different** |
| Session index | None | `sessions-index.json` | **Missing** |
| Schema | Custom | Claude-compatible | **Different** |
| Idempotent reprocessing | No | Yes (deterministic IDs) | **Missing** |

### Schema Comparison

**Current:**
```json
{
  "metadata": {...},
  "messages": [{role, content}, ...],
  "raw_text": "..."
}
```

**Target:**
```jsonl
{"type": "session_meta", "sessionId": "...", "app": "ollama", ...}
{"sessionId": "...", "uuid": "...", "parentUuid": null, "type": "user", "message": {...}}
{"sessionId": "...", "uuid": "...", "parentUuid": "...", "type": "assistant", "message": {...}}
```

---

## 9. Dependencies

- `pyte` (Python) - terminal emulation
- `script` (Unix) - session capture
- `perl` - ANSI stripping
- `python3` - conversion/analysis

---

## Next Steps (Task #2)

1. Design schema migration from current to target format
2. Implement deterministic UUID generation
3. Add parent chain threading
4. Create sessions-index.json generation
5. Update ai_export.py to produce JSONL
6. Ensure idempotent reprocessing capability
