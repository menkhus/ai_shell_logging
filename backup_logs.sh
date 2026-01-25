#!/bin/bash
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
#
# backup_logs.sh - Backup Claude Code and AI shell logs
#
# Protects your valuable session history from rotation/loss.
# Creates timestamped tarball in specified backup location.
#
# Usage: ./backup_logs.sh [backup_dir]
# Default backup_dir: ~/ai_log_backups

BACKUP_DIR="${1:-$HOME/ai_log_backups}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/ai_logs_backup_$TIMESTAMP.tar.gz"

CLAUDE_DIR="$HOME/.claude/projects"
AI_LOGS="$HOME/ai_shell_logs"

echo "========================================"
echo "AI LOG BACKUP"
echo "========================================"
echo ""
echo "Timestamp: $TIMESTAMP"
echo "Backup to: $BACKUP_FILE"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Check what we're backing up
echo "Sources:"
if [ -d "$CLAUDE_DIR" ]; then
    CLAUDE_SIZE=$(du -sh "$CLAUDE_DIR" 2>/dev/null | cut -f1)
    echo "   ~/.claude/projects: $CLAUDE_SIZE"
else
    echo "   ~/.claude/projects: NOT FOUND"
fi

if [ -d "$AI_LOGS" ]; then
    AI_SIZE=$(du -sh "$AI_LOGS" 2>/dev/null | cut -f1)
    echo "   ~/ai_shell_logs: $AI_SIZE"
else
    echo "   ~/ai_shell_logs: NOT FOUND"
fi

echo ""
echo "Creating backup..."

# Build tar command with existing directories
TAR_SOURCES=""
[ -d "$CLAUDE_DIR" ] && TAR_SOURCES="$TAR_SOURCES $CLAUDE_DIR"
[ -d "$AI_LOGS" ] && TAR_SOURCES="$TAR_SOURCES $AI_LOGS"

if [ -z "$TAR_SOURCES" ]; then
    echo "ERROR: No log directories found to backup"
    exit 1
fi

# Create the backup
tar -czf "$BACKUP_FILE" $TAR_SOURCES 2>/dev/null

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    echo ""
    echo "✅ Backup complete!"
    echo "   File: $BACKUP_FILE"
    echo "   Size: $BACKUP_SIZE"
    echo ""

    # Show recent backups
    echo "Recent backups in $BACKUP_DIR:"
    ls -lht "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -5
else
    echo "❌ Backup failed!"
    exit 1
fi

echo ""
echo "========================================"
echo "To restore:"
echo "   cd / && tar -xzf $BACKUP_FILE"
echo "========================================"
