#!/bin/bash
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
#
# setup_backup_schedule.sh - Set up weekly automated backup of AI logs
#
# Creates a macOS Launch Agent to run backup_logs.sh weekly.
# Uses launchd (native macOS scheduler), not cron.
#
# Usage: ./setup_backup_schedule.sh [install|uninstall|status]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_logs.sh"
PLIST_NAME="com.user.ai-log-backup"
PLIST_FILE="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_FILE="$HOME/ai_log_backups/backup.log"

show_status() {
    echo "========================================"
    echo "AI LOG BACKUP SCHEDULE STATUS"
    echo "========================================"
    echo ""
    echo "Launch Agent: $PLIST_FILE"

    if [ -f "$PLIST_FILE" ]; then
        echo "Status: INSTALLED"
        echo ""

        # Check if loaded
        if launchctl list | grep -q "$PLIST_NAME"; then
            echo "Loaded: YES (active)"
        else
            echo "Loaded: NO (installed but not running)"
        fi

        echo ""
        echo "Schedule: Weekly (Sundays at 2:00 AM)"
        echo "Log file: $LOG_FILE"

        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Last backup log:"
            tail -20 "$LOG_FILE"
        fi
    else
        echo "Status: NOT INSTALLED"
        echo ""
        echo "Run: $0 install"
    fi
    echo "========================================"
}

install_agent() {
    echo "Installing AI log backup schedule..."
    echo ""

    # Ensure backup script is executable
    chmod +x "$BACKUP_SCRIPT"

    # Create LaunchAgents directory if needed
    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$HOME/ai_log_backups"

    # Create the plist
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${BACKUP_SCRIPT}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>

    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

    echo "Created: $PLIST_FILE"

    # Load the agent
    launchctl load "$PLIST_FILE" 2>/dev/null

    if [ $? -eq 0 ]; then
        echo "Loaded into launchd"
        echo ""
        echo "✅ Installation complete!"
        echo ""
        echo "Schedule: Every Sunday at 2:00 AM"
        echo "Backups:  ~/ai_log_backups/"
        echo "Log:      $LOG_FILE"
        echo ""
        echo "To run immediately: $BACKUP_SCRIPT"
        echo "To check status:    $0 status"
        echo "To uninstall:       $0 uninstall"
    else
        echo "⚠️  Could not load agent (may already be loaded)"
        echo "Try: launchctl unload '$PLIST_FILE' && launchctl load '$PLIST_FILE'"
    fi
}

uninstall_agent() {
    echo "Uninstalling AI log backup schedule..."

    if [ -f "$PLIST_FILE" ]; then
        launchctl unload "$PLIST_FILE" 2>/dev/null
        rm "$PLIST_FILE"
        echo "✅ Removed: $PLIST_FILE"
        echo ""
        echo "Note: Existing backups in ~/ai_log_backups/ were NOT deleted."
    else
        echo "Not installed."
    fi
}

# Main
case "${1:-status}" in
    install)
        install_agent
        ;;
    uninstall)
        uninstall_agent
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 [install|uninstall|status]"
        exit 1
        ;;
esac
