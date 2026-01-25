# Session Log Pattern (Derived from Claude Code)

Pattern for converting raw terminal logs (ollama, gemini, etc.) into structured session data compatible with Claude's native format.

## Claude's Native Structure

### Session Index (`sessions-index.json`)
```json
{
  "version": 1,
  "entries": [
    {
      "sessionId": "823af9d6-f456-4dff-8265-026dfc14edff",
      "fullPath": "/path/to/session.jsonl",
      "firstPrompt": "how do I...",
      "summary": "Brief description of session",
      "messageCount": 14,
      "created": "2026-01-24T18:57:04.081Z",
      "modified": "2026-01-24T19:13:45.903Z",
      "projectPath": "/Users/mark/src/project",
      "gitBranch": "main"
    }
  ]
}
```

### Message Records (JSONL, one per line)
```json
{
  "sessionId": "823af9d6-f456-4dff-8265-026dfc14edff",
  "uuid": "23d39ed7-13cb-49e3-a115-1616a4c4a176",
  "parentUuid": null,
  "timestamp": "2026-01-24T19:33:11.944Z",
  "type": "user",
  "message": {
    "role": "user",
    "content": "the actual prompt text"
  }
}
```

```json
{
  "sessionId": "823af9d6-f456-4dff-8265-026dfc14edff",
  "uuid": "7a2b3c4d-...",
  "parentUuid": "23d39ed7-13cb-49e3-a115-1616a4c4a176",
  "timestamp": "2026-01-24T19:33:15.520Z",
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": "the response text"
  }
}
```

## Synthetic Pattern for Terminal Logs

### Key Difference: Deterministic UUIDs

Claude uses random `uuid4`. For terminal logs, use deterministic `uuid5` so:
- Re-processing produces identical IDs (idempotent)
- References remain stable across re-indexing
- Deduplication is trivial

### Session ID Generation
```python
from uuid import uuid5, NAMESPACE_URL
from pathlib import Path
from datetime import datetime

def generate_session_id(log_path: Path, start_time: datetime) -> str:
    """Deterministic session ID from source file and start time."""
    # Include app name in namespace for cross-tool uniqueness
    app = log_path.parent.name  # e.g., "ollama", "gemini"
    key = f"{app}:{log_path.name}:{start_time.isoformat()}"
    return str(uuid5(NAMESPACE_URL, key))
```

### Message ID Generation
```python
def generate_message_id(session_id: str, turn_number: int) -> str:
    """Deterministic message ID within session."""
    from uuid import UUID
    return str(uuid5(UUID(session_id), f"turn:{turn_number}"))
```

### Parent Chain
```
turn 0 (user)     → parentUuid: null
turn 1 (assistant) → parentUuid: turn_0_uuid
turn 2 (user)      → parentUuid: turn_1_uuid
turn 3 (assistant) → parentUuid: turn_2_uuid
...
```

## Output Schema for Processed Terminal Logs

### Per-Session File: `{session_id}.jsonl`
```json
{"type": "session_meta", "sessionId": "...", "app": "ollama", "model": "llama3", "sourceFile": "2026-01-24_121414.log", "created": "...", "cwd": "/path/if/known"}
{"sessionId": "...", "uuid": "...", "parentUuid": null, "timestamp": "...", "type": "user", "message": {"role": "user", "content": "prompt text"}}
{"sessionId": "...", "uuid": "...", "parentUuid": "...", "timestamp": "...", "type": "assistant", "message": {"role": "assistant", "content": "response text"}}
```

### Session Index: `sessions-index.json`
```json
{
  "version": 1,
  "app": "ollama",
  "entries": [
    {
      "sessionId": "...",
      "fullPath": "/path/to/processed/session.jsonl",
      "sourceFile": "/path/to/raw/2026-01-24_121414.log",
      "firstPrompt": "how do I...",
      "messageCount": 8,
      "created": "2026-01-24T12:14:14.000Z",
      "modified": "2026-01-24T12:45:00.000Z",
      "model": "llama3"
    }
  ]
}
```

## Processing Pipeline

```
raw .log file
    ↓
strip ANSI codes (regex: \x1b\[[0-9;]*[a-zA-Z])
    ↓
identify prompt/response boundaries
    ↓
extract timestamps (from filename + relative timing if available)
    ↓
generate deterministic session_id
    ↓
generate deterministic message uuids with parent chain
    ↓
write {session_id}.jsonl
    ↓
update sessions-index.json
    ↓
delete raw .log (optional, after verification)
```

## Directory Structure

```
~/ai_shell_logs/
├── ollama/
│   ├── raw/                    # original script captures (optional keep)
│   ├── sessions/               # processed JSONL
│   │   ├── {session_id}.jsonl
│   │   └── ...
│   └── sessions-index.json
├── gemini/
│   ├── sessions/
│   └── sessions-index.json
└── claude/                     # can skip - use native ~/.claude/projects/
```

## Recall Integration

The processed sessions follow Claude's pattern, so recall.py can index them uniformly:

```python
def index_ai_sessions():
    # Claude native
    for project in Path("~/.claude/projects").expanduser().iterdir():
        for jsonl in project.glob("*.jsonl"):
            index_session(jsonl, source="claude")

    # Processed terminal logs
    for app in ["ollama", "gemini"]:
        sessions_dir = Path(f"~/ai_shell_logs/{app}/sessions").expanduser()
        for jsonl in sessions_dir.glob("*.jsonl"):
            index_session(jsonl, source=app)
```

## Reference Fields

| Field | Purpose |
|-------|---------|
| `sessionId` | Stable reference to entire conversation |
| `uuid` | Stable reference to specific message |
| `parentUuid` | Conversation threading |
| `sourceFile` | Traceability to original log |
| `firstPrompt` | Quick identification without reading file |
| `app` | Which AI tool (ollama, gemini, claude) |
| `model` | Specific model if known |

## Why This Matters

1. **Unified recall** - Search across all AI conversations regardless of source
2. **Stable references** - Link to specific exchanges from notes, code comments
3. **Prompt/response pairs** - The unit of value for context recovery
4. **Idempotent processing** - Re-run safely, same IDs every time
