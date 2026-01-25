# Plan for GitHub Reusability

This document tracks work to make this project usable by others.

## Critical Issues

### 1. No LICENSE
- [x] Add MIT LICENSE file
- Impact: People can't legally use/fork without explicit license

### 2. No requirements.txt
- [x] Create requirements.txt with `pyte>=0.8.0`
- Impact: Users don't know what to install

### 3. No .gitignore
- [x] Add .gitignore for `__pycache__/`, `*.pyc`, `.DS_Store`
- Impact: Noise in repo, accidental commits

### 4. Hardcoded paths (15 files affected)
- [ ] Make `AI_LOG_DIR` configurable in ai_logging.zsh
- [ ] Update Python scripts to use environment variable or config
- Affected files:
  - `ai_export.py`
  - `ai_logging.zsh`
  - `session_index.py`
  - `cwd_drift_check.py`
  - `IMPROVEMENT_PLAN.md`
  - `todo.md`
  - `current_methodology_audit.md`
  - `session_log_pattern_derived_from_claude.md`
  - `vulnerablity_spitballing_for_local_coding_tools.md`
  - `SESSION_CHECKPOINT_2026-01-23.md`
  - `LAUNCHD_GUIDE.md`
  - `backup_logs.sh`
  - `analyze_with_ollama.sh`
  - `CLAUDE_SESSION_LOGS.md`
  - `README.md`

### 5. No configuration system
- [ ] Define `AI_LOG_DIR` environment variable convention
- [ ] Document in README.md
- [ ] Default to `~/ai_shell_logs` if unset

## Structural Improvements

### 6. Consolidate documentation
- [ ] Decide: merge READMEs or rename to README.md + ARCHITECTURE.md
- Current state:
  - `README.md` - usage guide
  - `readme_first_about_this_project.md` - architecture overview

### 7. Add install script
- [ ] Create `install.sh` that:
  - Creates log directory
  - Checks for Python 3
  - Installs pyte via pip
  - Offers to add source line to .zshrc
  - Validates installation

### 8. Separate core from research
- [ ] Consider directory structure:
  ```
  core/           # Reusable logging infrastructure
    ai_logging.zsh
    ai_export.py
    session_converter.py
    session_index.py
  research/       # Analysis tools (optional for users)
    session_forensics.py
    sprint_runner.py
    capture_schema.py
    metrics_compare.py
    data_tool/
  docs/           # Documentation
    *.md files
  ```
- [ ] Or: keep flat but document which files are core vs research

## Quick Wins (do first)

1. LICENSE - 1 file, immediate legal clarity
2. requirements.txt - 1 file, immediate usability
3. .gitignore - 1 file, cleaner repo

## Progress Log

| Date | Item | Status |
|------|------|--------|
| 2026-01-25 | LICENSE, requirements.txt, .gitignore | Done |
