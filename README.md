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
├── ollama/
│   ├── sessions/                    # Claude-compatible JSONL
│   │   └── {session-uuid}.jsonl
│   ├── sessions-index.json          # Session index for queries
│   ├── raw/                         # Archived raw logs
│   │   └── 2026-01-25_125420.log
│   ├── 2026-01-25_125420.txt        # Clean readable text
│   └── 2026-01-25_125420.meta       # Session metadata
├── gemini/
│   └── (same structure)
└── claude/
    └── (same structure)
```

After each session, logs are automatically post-processed:
- `sessions/{uuid}.jsonl` - Claude-compatible JSONL with UUIDs and parent chains
- `sessions-index.json` - Queryable index of all sessions
- `.txt` - Clean, readable terminal output
- `.meta` - Enhanced session metadata (see below)
- `raw/*.log` - Archived raw logs
- `.error` - Error details (only if processing failed)

### Enhanced Metadata

Each session captures rich context for later recall:

```json
{
  "app": "ollama",
  "startTime": "2026-01-25T12:54:20-08:00",
  "endTime": "2026-01-25T13:42:15-08:00",
  "duration": "47m55s",
  "cwd": "/Users/mark/src/myproject",
  "gitBranch": "feature/auth-refactor",
  "gitCommitBefore": "a1b2c3d",
  "gitCommitAfter": "h7i8j9k",
  "gitCommitsMade": "d4e5f6g Add quicksort\nh7i8j9k Fix edge case",
  "filesModified": "src/sort.py,tests/test_sort.py",
  "tag": "sorting algorithms"
}
```

| Field | Description |
|-------|-------------|
| `startTime` / `endTime` | Session timing |
| `duration` | Human-readable duration (e.g., "47m55s") |
| `cwd` | Working directory when session started |
| `gitBranch` | Git branch (if in a repo) |
| `gitCommitBefore` / `After` | HEAD before and after session |
| `gitCommitsMade` | Commits created during session |
| `filesModified` | Files changed (via git diff) |
| `tag` | Optional user-provided tag |

### Migration Status (2026-01-25)

All sessions migrated to Claude-compatible JSONL format:

| App | JSONL Sessions | Index Entries |
|-----|----------------|---------------|
| ollama | 3 | 3 |
| gemini | 7 | 7 |
| claude | 14 | 14 |

## Breadcrumbs Philosophy

This tool is designed for **retrieval, recollection, and reuse** - not deep forensics. It captures:

- **What you asked** - your prompts
- **What happened** - the conversation
- **Where you were** - working directory, git branch
- **What changed** - commits made, files modified
- **When** - start time, end time, duration

Think of it as a **lab notebook for AI conversations**. The fidelity doesn't need to be perfect - it's about being able to find and recall what you did.

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

# Session index queries
ai_sessions ollama        # List recent ollama sessions
ai_sessions -a            # List sessions for all apps
ai_stats ollama           # Show index statistics
```

## Post-Processing

Raw logs contain ANSI escape codes. Use these tools to make them readable:

```bash
# Strip ANSI codes for readable text
ai_clean ~/ai_shell_logs/claude/2026-01-22_143052.log

# Export to clean text using terminal emulation (best results)
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log

# Export to Claude-compatible JSONL (recommended)
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log --jsonl

# Export JSONL and update session index
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log --jsonl --index

# Export to legacy JSON format (deprecated)
ai_export ~/ai_shell_logs/claude/2026-01-22_143052.log --json
```

### Session Management

```bash
# List recent sessions
ai_sessions ollama

# List sessions for all apps
ai_sessions -a

# Show session index statistics
ai_stats ollama

# Migrate legacy files to JSONL
ai_migrate --status      # Check migration status
ai_migrate ollama        # Migrate specific app
ai_migrate --all         # Migrate all apps
```

### JSONL Schema (Claude-compatible)

The `--jsonl` output uses deterministic UUIDs for idempotent reprocessing:

```jsonl
{"type": "session_meta", "sessionId": "uuid", "app": "ollama", "messageCount": 4, ...}
{"sessionId": "uuid", "uuid": "msg-uuid", "parentUuid": null, "type": "user", "message": {...}}
{"sessionId": "uuid", "uuid": "msg-uuid", "parentUuid": "prev-uuid", "type": "assistant", "message": {...}}
```

| Field | Description |
|-------|-------------|
| `sessionId` | Deterministic UUID5 from app + filename + timestamp |
| `uuid` | Deterministic message UUID5 within session |
| `parentUuid` | Links to previous message (conversation threading) |
| `type` | `"session_meta"`, `"user"`, or `"assistant"` |
| `message` | `{"role": "user"\|"assistant", "content": "..."}` |

### Session Index

Each app has a `sessions-index.json` for fast querying:

```json
{
  "version": 1,
  "app": "ollama",
  "entries": [
    {
      "sessionId": "uuid",
      "fullPath": "/path/to/session.jsonl",
      "firstPrompt": "How do I implement quicksort...",
      "messageCount": 8,
      "created": "2026-01-25T12:54:20Z",
      "duration": "47m55s",
      "cwd": "/Users/mark/src/myproject",
      "gitBranch": "feature/auth-refactor",
      "gitCommits": "d4e5f6g Add quicksort",
      "filesModified": "src/sort.py,tests/test_sort.py",
      "tag": "sorting algorithms"
    }
  ]
}
```

The `ai_sessions` command displays this in a readable format:

```
$ ai_sessions ollama --recent 3

2026-01-25  47m55s  feature/auth-refactor  [sorting algorithms]
  "How do I implement quicksort..."
  → 2 commit(s), 2 file(s)

2026-01-25  12m30s  main
  "Explain Python decorators..."

2026-01-24  5m10s  main  [debugging]
  "Why is my loop not terminating..."
  → 1 commit(s), 1 file(s)
```

### Legacy JSON Schema (deprecated)

The `--json` output provides the old format:

```json
{
  "metadata": {
    "exported_at": "2026-01-22T14:25:42.203664",
    "format_version": "1.0",
    "source_file": "/path/to/log"
  },
  "messages": [
    {"role": "user", "content": "Your prompt here..."},
    {"role": "assistant", "content": "Claude's response..."}
  ],
  "raw_text": "Full rendered terminal output..."
}
```

### Requirements

`ai_export` requires the `pyte` library:

```bash
pip install pyte
```

**Note:** Some versions of pyte may show a warning about `select_graphic_rendition()` getting an unexpected keyword argument. This is a minor compatibility issue that doesn't affect conversion results.

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
            ├── Session index (ai_sessions, ai_stats, ai_migrate)
            │
            ├── Tagging (ai_tag, ai_tags)
            │
            └── Post-processing (ai_clean, ai_export)
                    ├── ai_export.py (pyte terminal emulation)
                    ├── session_converter.py (JSONL conversion)
                    ├── session_index.py (index management)
                    └── migrate_sessions.py (legacy migration)
```

Data flows:
1. You run `claude` → wrapper logs to `~/ai_shell_logs/claude/<timestamp>.log`
2. Metadata written to `<timestamp>.meta` (JSON with tag, timestamp)
3. Session ends → automatic post-processing runs
4. On success: creates `.txt` + `sessions/{uuid}.jsonl`, updates index, archives raw log to `raw/`
5. On failure: writes `.error` file, preserves raw `.log`, notifies user

## How It Works

Uses the classic Unix `script` command to record terminal sessions:
- `-q` - quiet mode, no "Script started" banner

Each wrapped command gets its own subdirectory under `~/ai_shell_logs/`.

## Relationship to Claude Code Native Logs

Claude Code maintains its own internal logs at `~/.claude/projects/`. These contain:
- Full tool_use/tool_result data (file reads, edits, bash commands)
- Thinking blocks and internal state
- Complete message structure

**AI Shell Logging is complementary, not redundant:**

| What you want to know | AI Shell Logging | Claude Native |
|-----------------------|------------------|---------------|
| "What was I working on Tuesday?" | ✓ Git branch, commits, files | ✗ |
| "How long was that session?" | ✓ Duration, start/end time | ✗ |
| "What directory was I in?" | ✓ cwd captured | ✗ |
| "What did I ask about?" | ✓ Readable .txt | JSONL only |
| "What tools did Claude use?" | ✗ | ✓ Full detail |
| "What was Claude thinking?" | ✗ | ✓ Thinking blocks |

**Why wrap Claude too?**

The `claude` wrapper captures context that Claude's native logs don't:
- Git state before/after (branch, commits made, files touched)
- Session timing (duration, not just timestamps)
- Working directory
- Human-readable output

This is lightweight breadcrumbs for recall, not a replacement for Claude's internal telemetry. Both serve different purposes.

## Future Ideas

- Search across logs (`ai_search "some idea"`) - partially addressed via session index queries
- Log rotation / cleanup for old logs
- Integration with context-planner (auto-capture before `/pivot`)
- Semantic search across all AI sessions using embeddings
- LLM-generated session summaries (via local ollama)
