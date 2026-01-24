#!/bin/bash
# log_depth.sh - Assess forensic depth of Claude Code session logs
#
# Shows: date range, session count, per-project breakdown
# Usage: ./log_depth.sh [claude_dir]

CLAUDE_DIR="${1:-$HOME/.claude/projects}"

echo "========================================"
echo "CLAUDE CODE LOG FORENSIC DEPTH"
echo "========================================"

echo ""
echo "📁 LOG LOCATION: $CLAUDE_DIR"

# Count sessions
SESSION_COUNT=$(find "$CLAUDE_DIR" -name "*.jsonl" -type f 2>/dev/null | wc -l | tr -d ' ')
echo "📊 TOTAL SESSIONS: $SESSION_COUNT"

echo ""
echo "📅 DATE RANGE:"
echo "   Oldest:"
find "$CLAUDE_DIR" -name "*.jsonl" -type f -exec stat -f "%Sm %N" -t "%Y-%m-%d %H:%M" {} \; 2>/dev/null | sort | head -3 | while read line; do
    echo "     $line"
done

echo "   Newest:"
find "$CLAUDE_DIR" -name "*.jsonl" -type f -exec stat -f "%Sm %N" -t "%Y-%m-%d %H:%M" {} \; 2>/dev/null | sort | tail -3 | while read line; do
    echo "     $line"
done

echo ""
echo "📂 BY PROJECT (top 15):"
for d in "$CLAUDE_DIR"/*/; do
    if [ -d "$d" ]; then
        count=$(ls "$d"*.jsonl 2>/dev/null | wc -l | tr -d ' ')
        if [ "$count" -gt 0 ]; then
            size=$(du -sh "$d" 2>/dev/null | cut -f1)
            echo "$count|$size|$(basename "$d")"
        fi
    fi
done | sort -t'|' -k1 -rn | head -15 | while IFS='|' read count size name; do
    printf "   %3s sessions (%s): %s\n" "$count" "$size" "$name"
done

echo ""
echo "💾 TOTAL SIZE:"
du -sh "$CLAUDE_DIR" 2>/dev/null

echo "========================================"
