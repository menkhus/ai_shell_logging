# Session Checkpoint: 2026-01-23

## Thread to Resume

Exploring the **potential for a local diff/cache layer** between AI tools (Claude Code, Gemini CLI) and the LLM backend. The goal is to study inefficiencies empirically before building anything.

### Key concepts from Gemini conversation (`gemini_chatlog_2025_0123.md`):

1. **Deterministic Proxy** - local layer that intercepts tool calls, maintains state, returns diffs instead of full content
2. **Greek ISA** - compact symbolic instruction set instead of verbose JSON
3. **Basis + Diff** - cache the "basis" (file state), only transit deltas
4. **Speculative Execution** - fan out parallel prompts against same cached basis, merge results locally
5. **"Fixing the user"** - improving prompt quality may outperform infrastructure optimization

### Empirical findings (from toolkit):

- **154 sessions**, 28 days, 115MB of forensic data
- **1.8% residual inefficiency** at tool layer (after 99% context caching)
- **17.5% of prompts** classified as speculation/explanation (better for Gemini?)
- **0.36 meandering score** (moderate topic drift in sessions)

## Toolkit Built

Location: `~/src/ai_shell_logging/`

| Script | Purpose |
|--------|---------|
| `opportunity_study.py` | Cross-session efficiency analysis |
| `session_forensics.py` | Prompt patterns, tool fitness, meandering |
| `analyze_with_ollama.sh` | Pipe prompts to local LLM for offline critique |
| `extract_tool_calls.py` | List tool calls from a session |
| `diff_potential.py` | Analyze cache/diff savings for file reads |
| `backup_logs.sh` | Backup logs to ~/ai_log_backups/ |
| `setup_backup_schedule.sh` | Manage weekly backup via launchd |
| `toolkit_status.sh` | Dashboard of logs and tools |
| `log_depth.sh` | Forensic depth assessment |
| `launchd_user_jobs.sh` | Show non-Apple launchd jobs |

## Infrastructure

- **Backup schedule**: Weekly, Sundays 2AM via launchd (`com.user.ai-log-backup`)
- **Backup location**: `~/ai_log_backups/`
- **Log sources**: `~/.claude/projects/` (structured JSONL), `~/ai_shell_logs/` (terminal captures)

## Open Questions

1. Can we prototype a minimal diff layer without modifying Claude Code?
2. What's the ROI of "fixing the user" vs building infrastructure?
3. Should speculation/research prompts go to Gemini instead of Claude Code?
4. How to operationalize the ollama prompt analysis as a feedback loop?

## To Resume

```bash
# See where we left off
cat ~/src/ai_shell_logging/SESSION_CHECKPOINT_2026-01-23.md

# Review the Gemini architecture discussion
less ~/src/ai_shell_logging/gemini_chatlog_2025_0123.md

# Check current toolkit status
~/src/ai_shell_logging/toolkit_status.sh

# Run prompt analysis offline
~/src/ai_shell_logging/analyze_with_ollama.sh
```

## Next Steps (when resuming)

1. Run ollama analysis, review output
2. Decide: prototype diff layer OR focus on prompt quality
3. If diff layer: design minimal MCP server or tool wrapper
4. If prompt quality: build feedback loop from ollama analysis
