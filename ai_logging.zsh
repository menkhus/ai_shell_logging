# ai_logging.zsh - Opt-in AI session logging
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
#
# Source this file in your ~/.zshrc:
#   source ~/src/ai_shell_logging/ai_logging.zsh

AI_LOG_DIR="${AI_LOG_DIR:-$HOME/ai_shell_logs}"

# Generic wrapper - logs to app-specific subdir
# Supports --tag "description" to tag the session
# Automatically post-processes logs after session ends
# Captures rich context: cwd, git state, timing, files modified
_logged_ai() {
    local app="$1"
    shift

    # Parse --tag argument (must come before app args)
    local tag=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tag)
                tag="$2"
                shift 2
                ;;
            --tag=*)
                tag="${1#--tag=}"
                shift
                ;;
            *)
                break
                ;;
        esac
    done

    local logdir="$AI_LOG_DIR/$app"
    mkdir -p "$logdir"
    local timestamp=$(date +%F_%H%M%S)
    local logfile="$logdir/${timestamp}.log"
    local metafile="$logdir/${timestamp}.meta"
    local cleanfile="$logdir/${timestamp}.txt"
    local jsonfile="$logdir/${timestamp}.json"
    local errorfile="$logdir/${timestamp}.error"

    # Capture session context
    local cwd="$PWD"
    local start_time=$(date -Iseconds)
    local git_branch=""
    local git_commit_before=""
    local in_git_repo="false"

    # Capture git context if in a repo
    if git rev-parse --git-dir &>/dev/null 2>&1; then
        in_git_repo="true"
        git_branch=$(git branch --show-current 2>/dev/null || echo "")
        git_commit_before=$(git rev-parse HEAD 2>/dev/null || echo "")
    fi

    # Write initial metadata file (will be updated after session)
    {
        echo "{"
        echo "  \"app\": \"$app\","
        echo "  \"startTime\": \"$start_time\","
        echo "  \"cwd\": \"$cwd\","
        echo "  \"gitBranch\": \"$git_branch\","
        echo "  \"gitCommitBefore\": \"$git_commit_before\","
        echo "  \"tag\": \"$tag\","
        echo "  \"logfile\": \"$cleanfile\""
        echo "}"
    } > "$metafile"

    if [[ -n "$tag" ]]; then
        echo "Logging to: $logfile (tag: $tag)"
    else
        echo "Logging to: $logfile"
    fi
    [[ -n "$git_branch" ]] && echo "Git branch: $git_branch"

    # Run the session
    script -q "$logfile" command "$app" "$@"

    # Capture end state
    local end_time=$(date -Iseconds)
    local git_commit_after=""
    local git_commits_made=""
    local files_modified=""

    if [[ "$in_git_repo" == "true" && -n "$git_commit_before" ]]; then
        git_commit_after=$(git rev-parse HEAD 2>/dev/null || echo "")
        if [[ "$git_commit_before" != "$git_commit_after" ]]; then
            git_commits_made=$(git log --oneline "$git_commit_before".."$git_commit_after" 2>/dev/null | head -10)
            files_modified=$(git diff --name-only "$git_commit_before" 2>/dev/null | head -20 | tr '\n' ',' | sed 's/,$//')
        fi
    fi

    # Calculate duration
    local start_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "${start_time%+*}" "+%s" 2>/dev/null || echo "0")
    local end_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "${end_time%+*}" "+%s" 2>/dev/null || echo "0")
    local duration_secs=$((end_epoch - start_epoch))
    local duration_fmt="${duration_secs}s"
    if [[ $duration_secs -ge 60 ]]; then
        local mins=$((duration_secs / 60))
        local secs=$((duration_secs % 60))
        duration_fmt="${mins}m${secs}s"
    fi

    # Write complete metadata file
    {
        echo "{"
        echo "  \"app\": \"$app\","
        echo "  \"startTime\": \"$start_time\","
        echo "  \"endTime\": \"$end_time\","
        echo "  \"duration\": \"$duration_fmt\","
        echo "  \"cwd\": \"$cwd\","
        echo "  \"gitBranch\": \"$git_branch\","
        echo "  \"gitCommitBefore\": \"$git_commit_before\","
        echo "  \"gitCommitAfter\": \"$git_commit_after\","
        echo "  \"gitCommitsMade\": \"$git_commits_made\","
        echo "  \"filesModified\": \"$files_modified\","
        echo "  \"tag\": \"$tag\","
        echo "  \"logfile\": \"$cleanfile\""
        echo "}"
    } > "$metafile"

    # Show session summary
    echo ""
    echo "Session ended ($duration_fmt)"
    [[ -n "$git_commits_made" ]] && echo "Commits made:" && echo "$git_commits_made" | sed 's/^/  /'
    [[ -n "$files_modified" ]] && echo "Files modified: $files_modified"

    # Post-process the log automatically
    echo "Post-processing log..."
    _postprocess_log "$logfile" "$cleanfile" "$jsonfile" "$errorfile" "$metafile"
}

# Post-process a raw log file into clean text and JSONL
# On success: creates .txt and sessions/{session_id}.jsonl, updates index, deletes raw .log
# On failure: writes .error file, keeps raw .log
_postprocess_log() {
    local logfile="$1"
    local cleanfile="$2"
    local jsonfile="$3"  # Unused in new format, kept for backward compat
    local errorfile="$4"
    local metafile="$5"
    local script_dir="${0:A:h}"

    # Try to export clean text
    local export_output
    if export_output=$(python3 "$script_dir/ai_export.py" "$logfile" 2>&1); then
        echo "$export_output" > "$cleanfile"
    else
        _log_postprocess_error "$logfile" "$errorfile" "text export" "$export_output"
        return 1
    fi

    # Build metadata args for JSONL export
    local meta_args=""
    if [[ -f "$metafile" ]]; then
        meta_args="--meta $metafile"
    fi

    # Try to export JSONL (new Claude-compatible format)
    if export_output=$(python3 "$script_dir/ai_export.py" "$logfile" --jsonl --index $meta_args 2>&1); then
        # Output goes to sessions/{session_id}.jsonl and index is updated
        echo "$export_output"
    else
        _log_postprocess_error "$logfile" "$errorfile" "JSONL export" "$export_output"
        return 1
    fi

    # Success - archive raw log file
    local app=$(basename "$(dirname "$logfile")")
    local raw_dir="$AI_LOG_DIR/$app/raw"
    mkdir -p "$raw_dir"
    mv "$logfile" "$raw_dir/"
    echo "Log processed: $cleanfile"
}

# Log a post-processing error
_log_postprocess_error() {
    local logfile="$1"
    local errorfile="$2"
    local stage="$3"
    local error_output="$4"
    local script_dir="${0:A:h}"

    # Write detailed error to file
    {
        echo "Post-processing error"
        echo "====================="
        echo "Timestamp: $(date -Iseconds)"
        echo "Stage: $stage"
        echo "Log file: $logfile"
        echo "Script: $script_dir/ai_export.py"
        echo ""
        echo "Error output:"
        echo "$error_output"
    } > "$errorfile"

    # Notify user on stdout
    echo ""
    echo "=========================================="
    echo "POST-LOG PROCESSING ERROR"
    echo "=========================================="
    echo "AI session logging completed successfully."
    echo "However, automatic post-processing failed."
    echo ""
    echo "Stage:     $stage"
    echo "Raw log:   $logfile (preserved)"
    echo "Error log: $errorfile"
    echo "Code:      $script_dir/ai_export.py"
    echo ""
    echo "You can manually process with:"
    echo "  ai_export $logfile"
    echo "=========================================="
}

# Opt-in wrappers - only these get logged
# Add or remove apps as needed
claude() { _logged_ai claude "$@"; }
ollama() { _logged_ai ollama "$@"; }
gemini() { _logged_ai gemini "$@"; }

# List recent logs
# Usage: ai_logs [app]
ai_logs() {
    local app="${1:-}"
    if [[ -n "$app" ]]; then
        ls -lt "$AI_LOG_DIR/$app"/*.log 2>/dev/null | head -10
    else
        find "$AI_LOG_DIR" -name "*.log" -type f -mtime -7 -exec ls -lt {} + 2>/dev/null | head -20
    fi
}

# Tail the most recent log for an app
# Usage: ai_tail <app>
ai_tail() {
    local app="$1"
    if [[ -z "$app" ]]; then
        echo "Usage: ai_tail <app>"
        echo "Apps: claude, ollama, gemini"
        return 1
    fi
    local latest=$(ls -t "$AI_LOG_DIR/$app"/*.log 2>/dev/null | head -1)
    if [[ -n "$latest" ]]; then
        tail -f "$latest"
    else
        echo "No logs for $app"
    fi
}

# Show current session log path (if in a logged session)
ai_session() {
    if [[ -n "$SESSION_LOGFILE" ]]; then
        echo "$SESSION_LOGFILE"
    else
        echo "Not in a logged session"
    fi
}

# Clean a log file by stripping ANSI escape codes
# Usage: ai_clean <logfile> [output_file]
# If output_file is omitted, prints to stdout
# For best results, use ai_export which properly emulates the terminal
ai_clean() {
    local logfile="$1"
    local outfile="$2"

    if [[ -z "$logfile" ]]; then
        echo "Usage: ai_clean <logfile> [output_file]"
        echo "Strips ANSI escape codes from script logs"
        echo "Note: For structured output, use ai_export instead"
        return 1
    fi

    if [[ ! -f "$logfile" ]]; then
        echo "Error: File not found: $logfile"
        return 1
    fi

    # Strip ANSI escape sequences and clean up using perl
    local cleaned
    cleaned=$(perl -pe '
        # Remove escape sequences: CSI (ESC [), OSC (ESC ]), and simple ESC codes
        s/\e\[[0-9;?]*[a-zA-Z]//g;   # CSI sequences (colors, cursor, modes)
        s/\e\][^\a\e]*(?:\a|\e\\)//g; # OSC sequences (title, etc)
        s/\e[()][0-9A-Z]//g;          # Character set selection
        s/\e[=>]//g;                  # Keypad modes
        s/\r//g;                      # Carriage returns
    ' "$logfile" |
    tr -d '\000' |                    # Remove null bytes
    perl -00 -pe '
        # Remove lines that are just single chars (keystroke echoes)
        s/^.\n//gm;
        # Collapse multiple blank lines
        s/\n{3,}/\n\n/g;
    ' |
    # Remove box-drawing artifacts and UI chrome, keep content
    grep -v '^[│╭╰├┤┌┐└┘─═╔╗╚╝║]*$' |
    cat -s)

    if [[ -n "$outfile" ]]; then
        echo "$cleaned" > "$outfile"
        echo "Cleaned log written to: $outfile"
    else
        echo "$cleaned"
    fi
}

# Export a log file to clean text, JSON, or JSONL using terminal emulation
# Usage: ai_export <logfile> [--json|--jsonl] [-o output_file]
# Requires: pip install pyte
ai_export() {
    local script_dir="${0:A:h}"
    python3 "$script_dir/ai_export.py" "$@"
}

# List sessions from the session index
# Usage: ai_sessions [app]        # List recent sessions
#        ai_sessions -a           # List all apps
ai_sessions() {
    local script_dir="${0:A:h}"
    local app="${1:-}"

    if [[ "$app" == "-a" || "$app" == "--all" ]]; then
        # List all apps
        for a in ollama gemini claude; do
            if [[ -f "$AI_LOG_DIR/$a/sessions-index.json" ]]; then
                echo "=== $a ==="
                python3 "$script_dir/session_index.py" "$a" --recent 5
                echo ""
            fi
        done
    elif [[ -n "$app" ]]; then
        python3 "$script_dir/session_index.py" "$app" --recent 10
    else
        echo "Usage: ai_sessions <app>    # List recent sessions"
        echo "       ai_sessions -a       # List all apps"
        echo "Apps: ollama, gemini"
    fi
}

# Show session index statistics
# Usage: ai_stats [app]
ai_stats() {
    local script_dir="${0:A:h}"
    local app="${1:-}"

    if [[ -n "$app" ]]; then
        python3 "$script_dir/session_index.py" "$app" --stats
    else
        for a in ollama gemini claude; do
            if [[ -f "$AI_LOG_DIR/$a/sessions-index.json" ]]; then
                echo "=== $a ==="
                python3 "$script_dir/session_index.py" "$a" --stats
                echo ""
            fi
        done
    fi
}

# Migrate legacy sessions to JSONL format
# Usage: ai_migrate [app]         # Migrate specific app
#        ai_migrate --all         # Migrate all apps
#        ai_migrate --status      # Show migration status
ai_migrate() {
    local script_dir="${0:A:h}"
    python3 "$script_dir/migrate_sessions.py" "$@"
}

# List sessions by tag or show all tags
# Usage: ai_tags              # List all unique tags
#        ai_tags <pattern>    # Find sessions matching tag pattern
ai_tags() {
    local pattern="${1:-}"

    if [[ -z "$pattern" ]]; then
        # List all unique tags
        echo "Tags:"
        find "$AI_LOG_DIR" -name "*.meta" -type f -exec cat {} \; 2>/dev/null |
            grep '"tag":' |
            sed 's/.*"tag": "\([^"]*\)".*/\1/' |
            grep -v '^$' |
            sort -u |
            while read -r tag; do
                local count=$(find "$AI_LOG_DIR" -name "*.meta" -exec grep -l "\"tag\": \"$tag\"" {} \; 2>/dev/null | wc -l | tr -d ' ')
                echo "  $tag ($count sessions)"
            done
    else
        # Find sessions matching tag pattern
        echo "Sessions tagged with '$pattern':"
        find "$AI_LOG_DIR" -name "*.meta" -type f -print0 2>/dev/null |
            while IFS= read -r -d '' metafile; do
                if grep -q "\"tag\": \".*$pattern.*\"" "$metafile" 2>/dev/null; then
                    local logfile="${metafile%.meta}.log"
                    local tag=$(grep '"tag":' "$metafile" | sed 's/.*"tag": "\([^"]*\)".*/\1/')
                    local ts=$(grep '"timestamp":' "$metafile" | sed 's/.*"timestamp": "\([^"]*\)".*/\1/')
                    echo "  $logfile"
                    echo "    Tag: $tag | Time: $ts"
                fi
            done
    fi
}

# Tag an existing log file retroactively
# Usage: ai_tag <logfile> <tag>
ai_tag() {
    local logfile="$1"
    local tag="$2"

    if [[ -z "$logfile" || -z "$tag" ]]; then
        echo "Usage: ai_tag <logfile> <tag>"
        echo "Add or update tag for an existing log file"
        return 1
    fi

    if [[ ! -f "$logfile" ]]; then
        echo "Error: Log file not found: $logfile"
        return 1
    fi

    local metafile="${logfile%.log}.meta"
    local app=$(basename "$(dirname "$logfile")")

    if [[ -f "$metafile" ]]; then
        # Update existing meta file - replace tag line
        local tmp=$(mktemp)
        sed "s/\"tag\": \"[^\"]*\"/\"tag\": \"$tag\"/" "$metafile" > "$tmp"
        mv "$tmp" "$metafile"
        echo "Updated tag to: $tag"
    else
        # Create new meta file
        local ts=$(stat -f "%Sm" -t "%Y-%m-%dT%H:%M:%S" "$logfile" 2>/dev/null || date -Iseconds)
        {
            echo "{"
            echo "  \"app\": \"$app\","
            echo "  \"timestamp\": \"$ts\","
            echo "  \"tag\": \"$tag\","
            echo "  \"logfile\": \"$logfile\""
            echo "}"
        } > "$metafile"
        echo "Created tag: $tag"
    fi
}
