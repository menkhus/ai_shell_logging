# AI Shell Logging - TODO

## Future Enhancements

### Session Recall
- [ ] `ai_search <pattern>` - full-text search across all sessions
- [ ] LLM-generated session summaries (pipe to local ollama)
- [ ] Semantic search using embeddings

### Maintenance
- [ ] Log rotation / cleanup for old sessions
- [ ] Prune raw/ archives after N days

### Analysis (Optional)
- [ ] Adapt forensics tools to work on ai_shell_logs format
- [ ] Unified reader for both Claude native and terminal captures
- [ ] Prompt quality classification for terminal-captured sessions

## Design Decisions

**Breadcrumbs, not forensics**: This tool captures what you need for recall (prompts, outputs, context) not internal telemetry. Claude's native logs at `~/.claude/projects/` serve that purpose.

**Keep all wrappers**: Even though Claude has native logging, the wrapper adds value (git context, timing, readable .txt output, consistent experience across tools).
