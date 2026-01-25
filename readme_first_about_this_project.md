# AI Shell Logging: A Self-Improvement Research Framework

This repository contains 7-8 interrelated projects built around a central thesis: **user prompt quality has more ROI than infrastructure changes** when working with AI coding assistants.

## What This Is

A transparent introspection framework for analyzing and improving how you interact with AI CLI tools (Claude Code, Ollama, Gemini). It captures sessions, analyzes patterns, and provides tools to measure whether behavioral changes actually improve outcomes.

## Project Inventory

### 1. AI Session Logging Infrastructure
**Files:** `ai_logging.zsh`, `ai_export.py`

Core logging system that wraps AI CLI commands to capture terminal sessions.

- Intercepts `claude`, `ollama`, `gemini` commands via shell functions
- Uses Unix `script` command for raw capture with ANSI codes
- Post-processes to clean `.txt` and structured `.json` formats
- Supports session tagging: `claude --tag "refactoring auth module"`

```
~/ai_shell_logs/
├── claude/
│   ├── 2026-01-22_143052.txt   # clean readable text
│   ├── 2026-01-22_143052.json  # structured conversation
│   └── 2026-01-22_143052.meta  # metadata with tag
├── ollama/
└── gemini/
```

### 2. Session Format Migration
**Files:** `session_converter.py`, `session_index.py`, `migrate_sessions.py`

Converts terminal captures to Claude-compatible JSONL format with deterministic UUIDs.

- UUID5-based IDs enable idempotent re-processing
- Parent chain threading (each message links to predecessor)
- JSONL output (one record per line, streaming-friendly)
- `sessions-index.json` for fast session lookup

### 3. Working Directory Drift Detection
**Files:** `cwd_drift_check.py`

Detects when LLM sessions have stale working directory references.

```bash
cwd_drift_check.py              # Check all sessions
cwd_drift_check.py --recent 5   # Check last 5 per project
```

Identifies:
- Sessions with multiple `cwd` values (you cd'd mid-session)
- Cross-project issues (session stored in wrong project directory)

### 4. Validation & Sprint Framework
**Files:** `sprint_runner.py`, `capture_schema.py`, `metrics_compare.py`

A/B testing framework for prompt quality interventions.

```bash
./sprint_runner.py start native      # Baseline sprint (no intervention)
./sprint_runner.py start focused     # With prompt clinic intervention
./sprint_runner.py capture "prompt"  # Capture each prompt
./sprint_runner.py end               # Generate summary
./sprint_runner.py compare s1 s2     # Compare results
```

Tracks: directive/scoped/actionable scores, red flags, session outcomes.

### 5. Session Forensics & Usage Analysis
**Files:** `session_forensics.py`, `opportunity_study.py`, `extract_tool_calls.py`, `diff_potential.py`

Analyze Claude Code usage patterns for self-improvement.

- **Prompt classification:** debugging, implementation, refactoring, exploration
- **Specificity measurement:** terse, brief, moderate, detailed
- **Meandering score:** topic drift within session
- **Token waste analysis:** redundant reads, cache miss opportunities

```bash
session_forensics.py --prompts      # Extract prompts for analysis
session_forensics.py --ollama       # Format for local LLM analysis
opportunity_study.py --json         # Full efficiency report
```

### 6. Prompt Quality Intervention (Prompt Clinic)
**Files:** `capture_schema.py` (flags and scoring logic)

Pre-flight checks for prompts before sending. Detects:

| Red Flag | Pattern |
|----------|---------|
| Research leak | "I wonder", "I'm curious" |
| Scope creep | "and also", "and maybe" |
| Introspection | "What do you think" |
| Unbounded | "Let's explore", "help me understand" |

Scoring (1-10 scale, no LLM required):
- **Directive:** Does it state a clear outcome?
- **Scoped:** Is it limited to ONE task?
- **Actionable:** Can work begin immediately?

### 7. Deep Session Data Extraction
**Files:** `data_tool/enhanced_extractor.py`, `data_tool/schema_analyzer.py`

Extracts 100% of Claude Code's internal JSONL data for research.

From 77 analyzed sessions:
- 13,555 message nodes with parent threading
- 7,640 API requests with correlation
- 3,165 tool executions with metrics
- 1,174 file snapshots

Key findings:
- 98% wasted thinking (reasoning with no following action)
- 37% todo completion rate
- 49% sessions healthy / 21% poor health

### 8. Backup Automation (launchd)
**Files:** `LAUNCHD_GUIDE.md`

macOS scheduled task setup for automated log backups.

## Data Flow

```
Terminal Session
       ↓
ai_logging.zsh (capture)
       ↓
ai_export.py (clean + structure)
       ↓
session_converter.py (JSONL + UUID)
       ↓
┌──────┴──────┐
↓             ↓
forensics   extraction
(prompts)   (full data)
       ↓
sprint validation
(A/B comparison)
```

All projects share deterministic UUID5 session IDs for perfect cross-correlation.

## Key Commands

```bash
# Shell integration (add to .zshrc)
source ~/src/ai_shell_logging/ai_logging.zsh

# Session management
ai_logs                    # List recent logs
ai_tail                    # Follow live session
ai_tag "description"       # Tag current session
ai_tags "search term"      # Search by tag

# Analysis
./session_forensics.py --prompts
./cwd_drift_check.py --recent 10
./sprint_runner.py compare native-01 focused-01

# Deep extraction
python data_tool/enhanced_extractor.py ~/path/to/session.jsonl
```

## Design Philosophy

1. **Opt-in logging** - Only captures tools you explicitly wrap
2. **Deterministic processing** - Idempotent operations enable re-runs
3. **Complete transparency** - Access to all internal Claude Code data
4. **Validation-first** - A/B test before implementing changes
5. **User behavior as target** - Prompt quality over infrastructure

## Related Documentation

- `IMPROVEMENT_PLAN.md` - Session format migration spec
- `current_methodology_audit.md` - Capture methods audit
- `EFFECTIVE_CLAUDE_USAGE.md` - Best practices derived from analysis
- `design_for_the_human.md` - Strategic design notes
- `todo.md` - Project status and roadmap
