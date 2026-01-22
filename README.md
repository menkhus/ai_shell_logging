# AI Shell Logging

Opt-in session logging for AI CLI tools.

## Problem

When working with AI assistants (Claude Code, Ollama, Gemini CLI), conversations are rich with ideas and context. Terminal scrollback is ephemeral - you lose it when the window closes.

General-purpose logging (logging everything) creates noise. You don't want vim sessions, quick git commands, etc.

## Solution

Wrapper functions that log only specific AI tools to application-specific directories.

## What Gets Logged

| Tool | Logged | Why |
|------|--------|-----|
| `claude` | Yes | Long sessions, rich context |
| `ollama` | Yes | Local AI conversations |
| `gemini` | Yes | Gemini CLI sessions |
| `vim` | No | Not useful to replay |
| `git` | No | Already has its own history |

## Directory Structure

```
~/ai_shell_logs/
├── claude/
│   ├── 2026-01-22_143052.log
│   ├── 2026-01-22_143052.meta   # JSON metadata with tag
│   └── 2026-01-22_091523.log
├── ollama/
│   └── 2026-01-22_102211.log
└── gemini/
    └── 2026-01-22_111847.log
```

## Installation

Add to your `~/.zshrc`:

```bash
source ~/src/ai_shell_logging/ai_logging.zsh
```

## Usage

```bash
claude              # Starts claude, session is logged
ollama run llama3   # Starts ollama, session is logged
vim foo.py          # Normal vim, not logged

ai_logs             # List all recent logs
ai_logs claude      # List recent claude logs
ai_tail claude      # Tail the most recent claude session (from another terminal)

# Tag a session when starting
claude --tag "refactoring auth"

# Tag an existing log retroactively
ai_tag ~/ai_shell_logs/claude/2026-01-22_143052.log "bug fix"

# List all tags
ai_tags

# Find sessions by tag pattern
ai_tags "auth"
```

## Post-Processing

Raw logs contain ANSI escape codes. Use these tools to make them readable:

```bash
# Strip ANSI codes for readable text
ai_clean ~/ai_shell_logs/claude/2026-01-22_143052.log

# Export to clean text using terminal emulation (best results)
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log

# Export to structured JSON
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log --json

# Save to file
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log --json -o session.json
```

### JSON Schema

The `--json` output provides structured access to conversation data:

```json
{
  "metadata": {
    "exported_at": "2026-01-22T14:25:42.203664",
    "format_version": "1.0",
    "source_file": "/Users/mark/ai_shell_logs/claude/2026-01-22_140505.log"
  },
  "messages": [
    {"role": "user", "content": "Your prompt here..."},
    {"role": "assistant", "content": "Claude's response..."}
  ],
  "raw_text": "Full rendered terminal output..."
}
```

| Key | Type | Description |
|-----|------|-------------|
| `metadata.exported_at` | string | ISO timestamp of export |
| `metadata.format_version` | string | Schema version for compatibility |
| `metadata.source_file` | string | Path to original log file |
| `messages[]` | array | Parsed conversation turns |
| `messages[].role` | string | `"user"` or `"assistant"` |
| `messages[].content` | string | Message content |
| `raw_text` | string | Complete rendered terminal output |

Example: Extract all user prompts from a session:

```bash
ai_export session.log --json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for msg in data['messages']:
    if msg['role'] == 'user':
        print(msg['content'])
"
```

### Requirements

`ai_export` requires the `pyte` library:

```bash
pip install pyte
```

## Architecture

This directory (`~/src/ai_shell_logging`) contains the integration tools. Your `~/.zshrc` sources the main script:

```
~/.zshrc
    └── source ~/src/ai_shell_logging/ai_logging.zsh
            │
            ├── Wrapper functions (claude, ollama, gemini)
            │       └── Intercept commands, log via `script`
            │
            ├── Log management (ai_logs, ai_tail, ai_session)
            │
            ├── Tagging (ai_tag, ai_tags)
            │
            └── Post-processing (ai_clean, ai_export)
                    └── ai_export.py (pyte terminal emulation)
```

Data flows:
1. You run `claude` → wrapper logs to `~/ai_shell_logs/claude/<timestamp>.log`
2. Metadata written to `<timestamp>.meta` (JSON with tag, timestamp)
3. Later: `ai_export` converts raw logs to readable text or structured JSON

## How It Works

Uses the classic Unix `script` command to record terminal sessions:
- `-q` - quiet mode, no "Script started" banner

Each wrapped command gets its own subdirectory under `~/ai_shell_logs/`.

## Future Ideas

- Search across logs (`ai_search "some idea"`)
- Log rotation / cleanup for old logs
- Integration with context-planner (auto-capture before `/pivot`)
