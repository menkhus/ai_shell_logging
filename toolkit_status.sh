#!/bin/bash
# toolkit_status.sh - Show status of AI logging toolkit and log retention
#
# Answers:
# - What tools do we have?
# - How much log data exists?
# - What's the retention situation?
# - Is there a rotation policy?
#
# Usage: ./toolkit_status.sh

SCRIPT_DIR="$(dirname "$0")"
CLAUDE_DIR="$HOME/.claude"
AI_LOGS="$HOME/ai_shell_logs"

echo "========================================"
echo "AI LOGGING TOOLKIT STATUS"
echo "========================================"

echo ""
echo "📦 TOOLKIT SCRIPTS:"
echo "   Location: $SCRIPT_DIR"
echo ""
find "$SCRIPT_DIR" -maxdepth 1 -type f \( -name "*.py" -o -name "*.sh" -o -name "*.zsh" \) | sort | while read f; do
    name=$(basename "$f")
    # Extract first comment line as description
    desc=$(head -5 "$f" | grep -m1 "^#.*-" | sed 's/^#[[:space:]]*//' | cut -c1-50)
    printf "   %-28s %s\n" "$name" "$desc"
done

echo ""
echo "========================================"
echo "📊 CLAUDE CODE LOGS:"
echo "   Location: $CLAUDE_DIR/projects"
echo ""

if [ -d "$CLAUDE_DIR/projects" ]; then
    SESSION_COUNT=$(find "$CLAUDE_DIR/projects" -name "*.jsonl" -type f 2>/dev/null | wc -l | tr -d ' ')
    TOTAL_SIZE=$(du -sh "$CLAUDE_DIR/projects" 2>/dev/null | cut -f1)
    OLDEST=$(find "$CLAUDE_DIR/projects" -name "*.jsonl" -type f -exec stat -f "%Sm" -t "%Y-%m-%d" {} \; 2>/dev/null | sort | head -1)
    NEWEST=$(find "$CLAUDE_DIR/projects" -name "*.jsonl" -type f -exec stat -f "%Sm" -t "%Y-%m-%d" {} \; 2>/dev/null | sort | tail -1)

    echo "   Sessions:    $SESSION_COUNT"
    echo "   Total size:  $TOTAL_SIZE"
    echo "   Date range:  $OLDEST to $NEWEST"
else
    echo "   No Claude logs found"
fi

echo ""
echo "========================================"
echo "📊 AI SHELL LOGS (script captures):"
echo "   Location: $AI_LOGS"
echo ""

if [ -d "$AI_LOGS" ]; then
    for app_dir in "$AI_LOGS"/*/; do
        if [ -d "$app_dir" ]; then
            app=$(basename "$app_dir")
            count=$(find "$app_dir" -maxdepth 1 -type f \( -name "*.log" -o -name "*.txt" -o -name "*.json" \) 2>/dev/null | wc -l | tr -d ' ')
            size=$(du -sh "$app_dir" 2>/dev/null | cut -f1)
            printf "   %-12s %3s files  %s\n" "$app:" "$count" "$size"
        fi
    done
else
    echo "   No AI shell logs found"
fi

echo ""
echo "========================================"
echo "⚠️  RETENTION POLICY:"
echo ""

# Check for any rotation config
if [ -f "$CLAUDE_DIR/settings.json" ]; then
    echo "   Claude settings.json exists - checking for rotation..."
    if grep -q "retention\|rotate\|cleanup" "$CLAUDE_DIR/settings.json" 2>/dev/null; then
        grep -i "retention\|rotate\|cleanup" "$CLAUDE_DIR/settings.json"
    else
        echo "   No rotation policy found in settings"
    fi
else
    echo "   No Claude settings.json found"
fi

echo ""
echo "   ⚡ IMPORTANT: Claude Code log retention is UNKNOWN."
echo "   Logs may be rotated by the application without notice."
echo "   RECOMMENDATION: Back up ~/.claude/projects regularly."
echo ""
echo "========================================"
