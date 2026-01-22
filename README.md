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
```

## How It Works

Uses the classic Unix `script` command to record terminal sessions:
- `-q` - quiet mode, no "Script started" banner
- `-f` - flush in real time (survives crashes)

Each wrapped command gets its own subdirectory under `~/ai_shell_logs/`.

## Future Ideas

- Log rotation / cleanup for old logs
- Search across logs (`ai_grep "some idea"`)
- Session tagging (`claude --tag "refactoring auth"`)
- Integration with context-planner (auto-capture before `/pivot`)
