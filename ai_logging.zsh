# ai_logging.zsh - Opt-in AI session logging
#
# Source this file in your ~/.zshrc:
#   source ~/src/ai_shell_logging/ai_logging.zsh

AI_LOG_DIR="${AI_LOG_DIR:-$HOME/ai_shell_logs}"

# Generic wrapper - logs to app-specific subdir
_logged_ai() {
    local app="$1"
    shift
    local logdir="$AI_LOG_DIR/$app"
    mkdir -p "$logdir"
    local logfile="$logdir/$(date +%F_%H%M%S).log"

    echo "Logging to: $logfile"
    script -q -f "$logfile" command "$app" "$@"
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
