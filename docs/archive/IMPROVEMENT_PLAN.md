# Improvement Plan: Claude-Compatible Session Logs

**Task:** Migrate terminal log processing to produce Claude-compatible JSONL format.

**Source:** `session_log_pattern_derived_from_claude.md`
**Audit:** `current_methodology_audit.md`

---

## Gap Summary

| Feature | Current | Target | Priority |
|---------|---------|--------|----------|
| Session ID | None | Deterministic UUID5 | P0 |
| Message ID | None | Deterministic UUID5 | P0 |
| Parent chain | None | parentUuid threading | P0 |
| Output format | Single .json | .jsonl (streaming) | P0 |
| Session index | None | sessions-index.json | P1 |
| Schema | Custom | Claude-compatible | P0 |
| Idempotent | No | Yes | P1 |

---

## Design Decisions

### 1. UUID Generation Strategy

**Session ID:**
```python
from uuid import uuid5, NAMESPACE_URL

def generate_session_id(app: str, filename: str, start_time: datetime) -> str:
    """Deterministic session ID from source identity."""
    key = f"{app}:{filename}:{start_time.isoformat()}"
    return str(uuid5(NAMESPACE_URL, key))
```

**Message ID:**
```python
def generate_message_id(session_id: str, turn_number: int) -> str:
    """Deterministic message ID within session."""
    return str(uuid5(UUID(session_id), f"turn:{turn_number}"))
```

**Rationale:**
- UUID5 is deterministic (same input → same output)
- Re-processing produces identical IDs
- Namespace separation prevents collisions across apps

### 2. Parent Chain Threading

```
Message 0 (user):      parentUuid = null
Message 1 (assistant): parentUuid = message_0_uuid
Message 2 (user):      parentUuid = message_1_uuid
Message 3 (assistant): parentUuid = message_2_uuid
...
```

Each message points to its predecessor, creating a linked list that preserves conversation order.

### 3. Output Format: JSONL

**Current (monolithic JSON):**
```json
{
  "metadata": {...},
  "messages": [...],
  "raw_text": "..."
}
```

**Target (JSONL, one record per line):**
```jsonl
{"type": "session_meta", "sessionId": "...", "app": "ollama", ...}
{"sessionId": "...", "uuid": "...", "type": "user", "message": {...}}
{"sessionId": "...", "uuid": "...", "type": "assistant", "message": {...}}
```

**Benefits:**
- Streaming processing (no full load required)
- Append-friendly (can add messages without rewriting)
- Consistent with Claude's native format

### 4. Session Index

**File:** `~/ai_shell_logs/{app}/sessions-index.json`

```json
{
  "version": 1,
  "app": "ollama",
  "entries": [
    {
      "sessionId": "uuid-here",
      "fullPath": "/path/to/session.jsonl",
      "sourceFile": "/path/to/original.log",
      "firstPrompt": "First 100 chars of first prompt...",
      "messageCount": 8,
      "created": "2026-01-24T12:14:14.000Z",
      "modified": "2026-01-24T12:45:00.000Z",
      "model": "llama3",
      "tag": "optional session tag"
    }
  ]
}
```

**Operations:**
- **Add session:** Append to entries, write atomically
- **Update session:** Find by sessionId, update fields
- **Remove session:** Filter out entry, write atomically
- **Query:** Load index, filter/search in memory

### 5. Directory Structure

```
~/ai_shell_logs/
├── ollama/
│   ├── raw/                        # Optional: keep original .log files
│   │   └── 2026-01-24_121414.log
│   ├── sessions/                   # Processed JSONL
│   │   └── {session_id}.jsonl
│   ├── sessions-index.json         # Session index
│   └── legacy/                     # Old format files (migration)
│       ├── *.txt
│       └── *.json
├── gemini/
│   └── (same structure)
└── claude/
    └── (skip - use native ~/.claude/projects/)
```

---

## Implementation Plan

### Phase 1: Core Conversion Module

**File:** `session_converter.py`

```python
class SessionConverter:
    """Convert parsed messages to JSONL format."""

    def __init__(self, app: str, source_file: Path, start_time: datetime):
        self.session_id = generate_session_id(app, source_file.name, start_time)
        self.app = app
        self.source_file = source_file
        self.messages = []

    def add_message(self, role: str, content: str, timestamp: datetime = None):
        """Add a message with auto-generated UUID and parent chain."""
        turn = len(self.messages)
        uuid = generate_message_id(self.session_id, turn)
        parent_uuid = self.messages[-1]["uuid"] if self.messages else None

        self.messages.append({
            "sessionId": self.session_id,
            "uuid": uuid,
            "parentUuid": parent_uuid,
            "timestamp": (timestamp or datetime.now()).isoformat() + "Z",
            "type": role,
            "message": {"role": role, "content": content}
        })

    def write_jsonl(self, output_path: Path):
        """Write session as JSONL file."""
        with open(output_path, 'w') as f:
            # Session metadata first
            meta = {
                "type": "session_meta",
                "sessionId": self.session_id,
                "app": self.app,
                "sourceFile": str(self.source_file),
                "created": self.messages[0]["timestamp"] if self.messages else None,
                "messageCount": len(self.messages)
            }
            f.write(json.dumps(meta) + "\n")

            # Then each message
            for msg in self.messages:
                f.write(json.dumps(msg) + "\n")
```

### Phase 2: Update ai_export.py

**Changes:**
1. Add `--jsonl` flag for new format (default after migration)
2. Keep `--json` for legacy format (deprecated)
3. Use SessionConverter for JSONL output
4. Auto-update sessions-index.json

**New signature:**
```bash
ai_export <logfile>                    # Clean text (unchanged)
ai_export <logfile> --jsonl            # New JSONL format
ai_export <logfile> --json             # Legacy JSON (deprecated)
ai_export <logfile> --jsonl --index    # JSONL + update index
```

### Phase 3: Session Index Manager

**File:** `session_index.py`

```python
class SessionIndex:
    """Manage sessions-index.json for an app."""

    def __init__(self, app: str):
        self.app = app
        self.index_path = Path.home() / "ai_shell_logs" / app / "sessions-index.json"
        self.entries = self._load()

    def add_session(self, session_id: str, jsonl_path: Path,
                    source_file: Path, first_prompt: str,
                    message_count: int, model: str = None, tag: str = None):
        """Add or update a session entry."""
        entry = {
            "sessionId": session_id,
            "fullPath": str(jsonl_path),
            "sourceFile": str(source_file),
            "firstPrompt": first_prompt[:100],
            "messageCount": message_count,
            "created": datetime.now().isoformat() + "Z",
            "modified": datetime.now().isoformat() + "Z",
            "model": model,
            "tag": tag
        }

        # Update existing or append
        existing = next((e for e in self.entries if e["sessionId"] == session_id), None)
        if existing:
            existing.update(entry)
        else:
            self.entries.append(entry)

        self._save()

    def _load(self) -> list:
        if self.index_path.exists():
            with open(self.index_path) as f:
                data = json.load(f)
            return data.get("entries", [])
        return []

    def _save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, 'w') as f:
            json.dump({
                "version": 1,
                "app": self.app,
                "entries": self.entries
            }, f, indent=2)
```

### Phase 4: Update Post-Processing Pipeline

**In `ai_logging.zsh`, update `_postprocess_log`:**

```bash
_postprocess_log() {
    local logfile="$1"
    local app="$2"

    # New: JSONL output
    local sessions_dir="$HOME/ai_shell_logs/$app/sessions"
    mkdir -p "$sessions_dir"

    # Run converter
    python3 ~/src/ai_shell_logging/ai_export.py "$logfile" --jsonl --index

    # Converter writes to sessions/ and updates index
    # On success, optionally archive raw log
}
```

### Phase 5: Migration Tool

**File:** `migrate_sessions.py`

```python
def migrate_legacy_sessions(app: str):
    """Migrate old .json files to new JSONL format."""
    legacy_dir = Path.home() / "ai_shell_logs" / app
    sessions_dir = legacy_dir / "sessions"
    sessions_dir.mkdir(exist_ok=True)

    for json_file in legacy_dir.glob("*.json"):
        if json_file.name == "sessions-index.json":
            continue

        # Load legacy format
        with open(json_file) as f:
            data = json.load(f)

        # Convert to new format
        converter = SessionConverter(
            app=app,
            source_file=json_file,
            start_time=parse_timestamp_from_filename(json_file.name)
        )

        for msg in data.get("messages", []):
            converter.add_message(msg["role"], msg["content"])

        # Write JSONL
        output_path = sessions_dir / f"{converter.session_id}.jsonl"
        converter.write_jsonl(output_path)

        # Update index
        index = SessionIndex(app)
        index.add_session(
            session_id=converter.session_id,
            jsonl_path=output_path,
            source_file=json_file,
            first_prompt=data["messages"][0]["content"] if data["messages"] else "",
            message_count=len(data["messages"])
        )

        # Move legacy file
        legacy_archive = legacy_dir / "legacy"
        legacy_archive.mkdir(exist_ok=True)
        json_file.rename(legacy_archive / json_file.name)
```

---

## Testing Strategy

### Unit Tests
- UUID generation is deterministic
- Parent chain is correct
- JSONL format is valid
- Index operations are atomic

### Integration Tests
- Full pipeline: raw log → JSONL + index
- Re-processing produces identical output
- Migration preserves message content

### Acceptance Criteria
1. `ai_export --jsonl` produces valid Claude-compatible JSONL
2. `sessions-index.json` is created and updated
3. Re-running on same log produces identical session/message IDs
4. Existing analysis tools can read new format
5. Migration tool converts all legacy files

---

## Rollout Plan

1. **Implement** session_converter.py, session_index.py
2. **Update** ai_export.py with --jsonl flag
3. **Test** on sample logs, verify idempotency
4. **Migrate** existing sessions with migrate_sessions.py
5. **Update** post-processing pipeline to use new format
6. **Deprecate** old --json flag after transition period

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `session_converter.py` | Create | Core JSONL conversion |
| `session_index.py` | Create | Index management |
| `migrate_sessions.py` | Create | Legacy migration |
| `ai_export.py` | Modify | Add --jsonl flag |
| `ai_logging.zsh` | Modify | Update post-processing |

---

## Success Metrics

- [ ] All new sessions produce JSONL format
- [ ] All legacy sessions migrated
- [ ] Re-processing is idempotent (same IDs)
- [ ] sessions-index.json exists for each app
- [ ] Recall can index all AI sessions uniformly
