# ai_logging.zsh - Opt-in AI session logging
#
# Source this file in your ~/.zshrc:
#   source ~/src/ai_shell_logging/ai_logging.zsh

AI_LOG_DIR="${AI_LOG_DIR:-$HOME/ai_shell_logs}"

# Generic wrapper - logs to app-specific subdir
# Supports --tag "description" to tag the session
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

    # Write metadata file
    {
        echo "{"
        echo "  \"app\": \"$app\","
        echo "  \"timestamp\": \"$(date -Iseconds)\","
        echo "  \"tag\": \"$tag\","
        echo "  \"logfile\": \"$logfile\""
        echo "}"
    } > "$metafile"

    if [[ -n "$tag" ]]; then
        echo "Logging to: $logfile (tag: $tag)"
    else
        echo "Logging to: $logfile"
    fi
    script -q "$logfile" command "$app" "$@"
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

# Export a log file to clean text or JSON using terminal emulation
# Usage: ai_export <logfile> [--json] [-o output_file]
# Requires: pip install pyte
ai_export() {
    local script_dir="${0:A:h}"
    python3 "$script_dir/ai_export.py" "$@"
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
