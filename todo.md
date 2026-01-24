# AI Shell Logging - Project Status

**Purpose**: Opt-in session logging and forensic analysis for AI CLI tools
**Created**: January 2026
**Status**: Core infrastructure complete, user intervention tools pending

---

## Completed Work

### Core Logging Infrastructure

- [x] **ai_logging.zsh** - Main zsh integration
  - Wrapper functions: `claude`, `ollama`, `gemini`
  - Log management: `ai_logs`, `ai_tail`, `ai_session`
  - Tagging: `ai_tag`, `ai_tags`
  - Post-processing: `ai_clean`, `ai_export`
  - Auto-creates `.txt`, `.json`, `.meta` files after sessions

- [x] **ai_export.py** - Terminal emulation export
  - Uses pyte library for accurate rendering
  - Strips ANSI codes, handles cursor movement
  - Outputs clean text or structured JSON
  - Parses conversation into user/assistant messages

### Analysis & Forensics Tools

- [x] **session_forensics.py** - Prompt pattern analysis
  - Classifies prompts: directive, exploratory, debugging
  - Measures tool fitness per prompt type
  - Calculates meandering score (topic drift)

- [x] **opportunity_study.py** - Cross-session efficiency
  - Token usage per tool call
  - Cache hit potential
  - Context waste measurement

- [x] **extract_tool_calls.py** - Tool call extraction
  - Lists all tool invocations from a session
  - Useful for debugging and pattern analysis

- [x] **diff_potential.py** - Cache/diff savings analysis
  - Identifies repeated file reads
  - Calculates potential savings from caching

- [x] **data_tool/schema_analyzer.py** - Namespace discovery
  - Maps Claude Code's internal data structures
  - Identifies extractable fields

- [x] **data_tool/enhanced_extractor.py** - Full extraction + analytics
  - 100% namespace coverage
  - Extracts: messages, file snapshots, queue ops, thinking, todos, API requests
  - Generates efficiency metrics and health scores

### Utility Scripts

- [x] **backup_logs.sh** - Backup to ~/ai_log_backups/
- [x] **setup_backup_schedule.sh** - Weekly backup via launchd (Sundays 2AM)
- [x] **toolkit_status.sh** - Dashboard showing log counts and tool status
- [x] **log_depth.sh** - Forensic depth assessment per session
- [x] **launchd_user_jobs.sh** - List non-Apple launchd jobs
- [x] **analyze_with_ollama.sh** - Pipe prompts to local LLM for offline critique

### Prompt Quality Tools

- [x] **prompt_clinic.sh** - Pre-process prompts before sending
  - Scores: directive, scoped, actionable (1-10 each)
  - Detects: research leaks, scope creep, introspection
  - Uses local Ollama for analysis
  - Suggests rewrites for low-scoring prompts

### Documentation

- [x] **README.md** - Installation, usage, JSON schema, architecture
- [x] **CLAUDE_CODE_SYSTEM_PROMPT.md** - Captured system prompt for reference
- [x] **CLAUDE_SESSION_LOGS.md** - Session log format documentation
- [x] **EFFECTIVE_CLAUDE_USAGE.md** - Usage patterns and best practices
- [x] **LAUNCHD_GUIDE.md** - macOS launchd setup guide
- [x] **design_for_the_human.md** - Strategic design for /focused_coding
- [x] **SESSION_CHECKPOINT_2026-01-23.md** - Resumption checkpoint
- [x] **gemini_chatlog_2025_0123.md** - Gemini architecture discussion
- [x] **vulnerablity_spitballing_for_local_coding_tools.md** - Security considerations
- [x] **data_tool/TODO.md** - Data extraction status and findings

---

## Key Findings (77 Sessions Analyzed)

### Efficiency Metrics

| Metric | Value | Insight |
|--------|-------|---------|
| Wasted thinking | 98% | Thinking blocks with no following action |
| Todo completion | 37% | Tasks started but not finished |
| Redundant tool calls | 1,239 | Same tool called consecutively |
| Sessions needing compaction | 33 | Depth > 100 messages |
| Error recovery rate | 54% | Half of error sessions recover |
| Session health | 49% healthy | 30% warning, 21% poor |

### Extracted Data Counts

| Data Type | Count |
|-----------|-------|
| Message nodes | 13,555 |
| File snapshots | 1,174 |
| Queue operations | 1,138 |
| Thinking metadata | 768 |
| Todos | 545 |
| API requests | 7,640 |
| Tool executions | 3,165 |
| Errors | 160 |
| Summaries | 265 |

### Actionable Insights

1. **De-escalate wandering** - Thinking > 500 chars with no tool → prompt for clarity
2. **Suggest compaction** - Depth > 100 → recommend /compact or new session
3. **Batch tool calls** - Same tool 3+ times → suggest batching
4. **Catch error spirals** - Errors > turns in last 5 messages → pause
5. **Track todo abandonment** - in_progress > 5 minutes → prompt for status

---

## Pending Work

### Phase 4: User Behavior Intervention

#### Validation First (Days 1-3)

- [ ] **Instrument prompt clinic** - Log before/after prompt state with session ID
- [x] **Create capture schema** - Define metrics for before/after comparison (capture_schema.py)
- [x] **Manual sprint: native mode** - Full capture, no intervention (sprint_runner.py)
- [x] **Manual sprint: focused mode** - Full capture, microsprint discipline (sprint_runner.py with heuristic scoring)
- [x] **Compare metrics** - Which numbers moved? (metrics_compare.py)
- [x] **Document anecdotes** - What felt different? (anecdotes.py)

#### Build Phase (Day 4+, if validated)

- [ ] **/focus skill** - Strategic work mode
  - Depth monitoring with compaction prompts
  - Redundancy detection with batching suggestions
  - Wandering detector (thinking without action)
  - Todo tracking with abandonment alerts
  - Reject exploratory prompts → redirect to /research
  - Assert/de-assert pattern (layer on Claude, not replacement)

- [ ] **/research skill** - Curiosity sandbox
  - Capture curiosity items with session ID linkage
  - No tool execution pressure
  - Scratchpad for findings
  - Clean exit with summary
  - Can reference: "What was I curious about in session X?"

- [ ] **/clinic skill** - Prompt pre-processor integration
  - Integrate prompt_clinic.sh into Claude workflow
  - Persist analysis outcomes with session ID
  - Build corpus of prompt patterns for community learning

- [ ] **Stash mechanism** - Session ID linked capture
  - Stash speculation automatically
  - Stash questions with session ID
  - Stash meandering for later review

- [ ] **Forward file integration** - Semantic state machine
  - Tells you the next step
  - Integrated with todo
  - `make forward` drives the process

---

## Open Questions

1. Can we prototype a minimal diff layer without modifying Claude Code?
2. What's the ROI of "fixing the user" vs building infrastructure?
3. Should speculation/research prompts go to Gemini instead of Claude Code?
4. How to operationalize the ollama prompt analysis as a feedback loop?
5. Is 98% wasted thinking actually waste, or necessary exploration?

---

## Architecture

```
~/.zshrc
    └── source ~/src/ai_shell_logging/ai_logging.zsh
            │
            ├── Wrapper functions (claude, ollama, gemini)
            │       └── Log via `script` to ~/ai_shell_logs/<app>/
            │
            ├── Auto post-processing on session end
            │       └── ai_export.py creates .txt + .json
            │
            ├── Log management (ai_logs, ai_tail, ai_session)
            │
            ├── Tagging (ai_tag, ai_tags)
            │
            └── Analysis tools
                    ├── session_forensics.py
                    ├── opportunity_study.py
                    ├── data_tool/enhanced_extractor.py
                    └── prompt_clinic.sh
```

### Data Flow

1. Run `claude` → wrapper logs to `~/ai_shell_logs/claude/<timestamp>.log`
2. Metadata written to `<timestamp>.meta` (JSON with tag, timestamp)
3. Session ends → auto post-processing runs
4. Success: creates `.txt` + `.json`, deletes raw `.log`
5. Failure: writes `.error`, preserves raw `.log`

### Log Sources

- **Terminal captures**: `~/ai_shell_logs/` (this project)
- **Claude Code internals**: `~/.claude/projects/` (structured JSONL)

---

## For the Claude Community

> "This AI is the most transparent, and I want to say I could not have done this without the transparency and traceability built into Claude Code. Debugging users is hard. Self-reflection is hard."

**Why this matters:**
- Claude Code's JSONL logs enable debugging user behavior
- Open instrumentation enables open research
- Community can replicate and extend

**The contribution:**
- Methodology for debugging user behavior with AI
- Validation framework for prompt quality interventions
- /focused_coding as a pattern, not just a tool

---

## Quick Reference

```bash
# Start a tagged session
claude --tag "refactoring auth"

# List sessions by tag
ai_tags "auth"

# Check toolkit status
./toolkit_status.sh

# Analyze prompts before sending
./prompt_clinic.sh "your prompt here"

# Run full session analysis
python3 data_tool/enhanced_extractor.py

# Export session to JSON
ai_export ~/ai_shell_logs/claude/session.log --json
```

---

## Resume Point

```bash
# Read this document
cat ~/src/ai_shell_logging/todo.md

# Check current toolkit status
./toolkit_status.sh

# Review the strategic design
cat ~/src/ai_shell_logging/design_for_the_human.md

# Start validation: instrument prompt clinic
```

Next focus: **Validation before building** - instrument, capture, compare, then decide.
