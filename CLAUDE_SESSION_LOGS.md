# Claude Code Session Logs

Claude Code maintains detailed session logs that capture far more than terminal output. These logs contain the complete internal state of each conversation: reasoning, tool calls, results, and metadata.

## Location

```
~/.claude/projects/<encoded-project-path>/
├── sessions-index.json           # Index of all sessions for this project
├── <session-id>.jsonl            # Full conversation log (one JSON object per line)
└── <session-id>/                 # Session working directory (tool outputs, etc.)
```

The project path is encoded by replacing `/` with `-`, e.g.:
- `/Users/mark/src/myproject` → `-Users-mark-src-myproject`

## Sessions Index

`sessions-index.json` provides a quick overview of all sessions:

```json
{
  "version": 1,
  "entries": [
    {
      "sessionId": "6bea3744-df59-4970-ba67-53f496f07483",
      "fullPath": "/Users/mark/.claude/projects/.../6bea3744-....jsonl",
      "firstPrompt": "this project creates logs...",
      "summary": "Log post-processing with automatic cleanup",
      "messageCount": 37,
      "created": "2026-01-22T21:12:00.542Z",
      "modified": "2026-01-22T21:33:06.007Z",
      "gitBranch": "main",
      "projectPath": "/Users/mark/src/ai_shell_logging"
    }
  ]
}
```

## Message Types

Each line in the `.jsonl` file is a JSON object with a `type` field:

| Type | Description |
|------|-------------|
| `user` | User input (prompts, tool results) |
| `assistant` | Model response (text, thinking, tool calls) |
| `system` | System messages |
| `file-history-snapshot` | State of tracked files |
| `summary` | Conversation summary (for context management) |

## Message Structure

### User Message

```json
{
  "type": "user",
  "uuid": "8f27ad40-2b69-41d9-b7df-a877a6c612c3",
  "parentUuid": null,
  "timestamp": "2026-01-22T21:12:00.542Z",
  "sessionId": "6bea3744-df59-4970-ba67-53f496f07483",
  "cwd": "/Users/mark/src/ai_shell_logging",
  "gitBranch": "main",
  "version": "2.1.16",
  "permissionMode": "default",
  "message": {
    "role": "user",
    "content": "How do I process these logs?"
  }
}
```

### Assistant Message

```json
{
  "type": "assistant",
  "uuid": "b521d3a2-3033-438e-aba2-087d9d53c31b",
  "parentUuid": "8f27ad40-2b69-41d9-b7df-a877a6c612c3",
  "timestamp": "2026-01-22T21:12:03.833Z",
  "requestId": "req_011CXP73JiJohQUjA8bScTHu",
  "message": {
    "model": "claude-opus-4-5-20251101",
    "role": "assistant",
    "content": [
      {
        "type": "thinking",
        "thinking": "The user wants to process logs. I should..."
      },
      {
        "type": "text",
        "text": "You can process these logs by..."
      },
      {
        "type": "tool_use",
        "id": "toolu_01TcdoWEVJdKYpbSw8rWJL1d",
        "name": "Read",
        "input": { "file_path": "/path/to/file" }
      }
    ],
    "usage": {
      "input_tokens": 10084,
      "output_tokens": 523,
      "cache_read_input_tokens": 10439
    }
  }
}
```

## Content Types (in assistant messages)

| Type | Description |
|------|-------------|
| `thinking` | Internal reasoning (extended thinking) |
| `text` | Response text shown to user |
| `tool_use` | Tool invocation with name and input |
| `tool_result` | Result returned from tool (in user messages) |

## Key Fields

| Field | Description |
|-------|-------------|
| `uuid` | Unique message identifier |
| `parentUuid` | Links to previous message (conversation threading) |
| `sessionId` | Groups messages into sessions |
| `timestamp` | ISO 8601 timestamp |
| `cwd` | Working directory at time of message |
| `gitBranch` | Git branch (if in a repo) |
| `usage` | Token counts and cache statistics |
| `isSidechain` | Whether this is an alternate conversation branch |

## Tool Architecture

Claude Code uses a client-server architecture where tools bridge the remote model and your local machine:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Anthropic Cloud                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Claude Model                                             │  │
│  │  - Receives prompts + tool definitions                    │  │
│  │  - Returns text, thinking, and tool_use requests          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ API (tool_use / tool_result)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Your Machine                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Claude Code CLI                                          │  │
│  │  - Sends prompts to API                                   │  │
│  │  - Executes tool_use requests locally                     │  │
│  │  - Returns tool_result to model                           │  │
│  │  - Renders output to terminal                             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│          ┌───────────────────┼───────────────────┐              │
│          ▼                   ▼                   ▼              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐        │
│  │ Built-in    │     │ MCP Servers │     │ File System │        │
│  │ Tools       │     │ (optional)  │     │ / Shell     │        │
│  │             │     │             │     │             │        │
│  │ Read, Write │     │ mcp__*      │     │ Bash cmds   │        │
│  │ Edit, Glob  │     │ tools       │     │ File I/O    │        │
│  │ Grep, Task  │     │             │     │             │        │
│  └─────────────┘     └─────────────┘     └─────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### Built-in Tools

These are hardcoded in Claude Code and execute locally:

| Tool | Purpose |
|------|---------|
| `Read` | Read file contents |
| `Write` | Create/overwrite files |
| `Edit` | Search-and-replace in files |
| `Glob` | Find files by pattern |
| `Grep` | Search file contents |
| `Bash` | Execute shell commands |
| `WebFetch` | Fetch URL content |
| `WebSearch` | Web search |
| `Task` | Spawn sub-agents |
| `TaskCreate`, `TaskUpdate`, `TaskList` | Todo management |
| `AskUserQuestion` | Interactive prompts |

### MCP Tools (Model Context Protocol)

External tools loaded via MCP servers. Configured in:
- `~/.claude.json` - Global MCP servers
- `.claude/settings.local.json` - Project-specific

MCP tools have namespaced names: `mcp__<server>__<tool>`

Example: `mcp__file-metadata__search_files`

MCP servers run as subprocesses communicating via stdin/stdout (stdio), HTTP, or Server-Sent Events (SSE).

### Tool Call Flow

1. **Model sends `tool_use`:**
   ```json
   {"type": "tool_use", "name": "Read", "input": {"file_path": "/foo/bar.txt"}}
   ```

2. **Claude Code executes locally** (reads the file)

3. **Claude Code returns `tool_result`:**
   ```json
   {"type": "tool_result", "tool_use_id": "toolu_01...", "content": "file contents..."}
   ```

4. **Model continues** with the result

The terminal shows a summary ("Reading /foo/bar.txt...") but the session logs capture the complete request and response.

### Why Tool Names Look "Internal"

The tool names (`Read`, `Bash`, `Edit`) are the API contract between Claude and Claude Code. Users see rendered UI:

| What's in the log | What user sees |
|-------------------|----------------|
| `{"name": "Read", "input": {"file_path": "/foo"}}` | `⏺ Read(/foo)` |
| `{"name": "Bash", "input": {"command": "ls"}}` | `⏺ Bash(ls) → file1 file2...` |
| `{"name": "Edit", "input": {...}}` | `⏺ Edit(file.py) → Updated` |

The logs preserve the raw tool calls; the terminal shows a human-friendly rendering.

## Use Cases

### 1. Extract All Tool Calls
```bash
grep '"tool_use"' session.jsonl | jq '.message.content[] | select(.type=="tool_use") | {name, input}'
```

### 2. Get Thinking/Reasoning
```bash
grep '"thinking"' session.jsonl | jq -r '.message.content[] | select(.type=="thinking") | .thinking'
```

### 3. Calculate Token Usage
```bash
grep '"assistant"' session.jsonl | jq '[.message.usage.output_tokens] | add'
```

### 4. List Files Read
```bash
grep '"Read"' session.jsonl | jq -r '.message.content[].input.file_path' 2>/dev/null | sort -u
```

### 5. Get Conversation as Markdown
```bash
grep -E '"(user|assistant)"' session.jsonl | jq -r '
  if .type == "user" then "## User\n" + .message.content
  else "## Assistant\n" + (.message.content[] | select(.type=="text") | .text)
  end'
```

### 6. Find Sessions by Keyword
```bash
grep -l "keyword" ~/.claude/projects/*/session-*.jsonl
```

## Comparison: Terminal Logs vs Session Logs

| Aspect | Terminal Logs | Session Logs |
|--------|---------------|--------------|
| Format | Raw text + ANSI | Structured JSONL |
| Thinking | Not captured | Full reasoning |
| Tool calls | Summary only | Complete I/O |
| Token usage | Not available | Per-message |
| Threading | Linear | Graph (parentUuid) |
| Timestamps | None | Per-message |
| Searchable | grep text | jq queries |

## Privacy Note

Session logs contain everything: your prompts, file contents read, command outputs, and Claude's reasoning. They are stored locally in `~/.claude/` and are not uploaded anywhere, but be aware of their contents if sharing or backing up.
