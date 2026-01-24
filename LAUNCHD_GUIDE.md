# macOS launchd Guide for User Scheduled Tasks

## What is launchd?

launchd is macOS's init system and service manager (like systemd on Linux).
It replaces cron, init, inetd, and more. For user-level scheduled tasks,
you create "Launch Agents."

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      launchd                            │
│                 (system process, PID 1)                 │
└─────────────────────┬───────────────────────────────────┘
                      │ reads
                      ▼
┌─────────────────────────────────────────────────────────┐
│              .plist files (job definitions)             │
│                                                         │
│  System-wide:  /Library/LaunchDaemons/                  │
│  System agents: /Library/LaunchAgents/                  │
│  User agents:   ~/Library/LaunchAgents/   ← YOU USE THIS│
└─────────────────────┬───────────────────────────────────┘
                      │ executes
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Your script (the workload)                 │
│         e.g., ~/src/ai_shell_logging/backup_logs.sh    │
└─────────────────────────────────────────────────────────┘
```

## The .plist File (Job Definition)

A .plist is an XML file that tells launchd:
- **Label**: Unique identifier (like "com.mark.ai-backup")
- **ProgramArguments**: What to run (your script)
- **StartCalendarInterval**: When to run (cron-like schedule)
- **StandardOutPath/StandardErrorPath**: Where to log output

Example:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mark.ai-backup</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/mark/src/ai_shell_logging/backup_logs.sh</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>  <!-- 0=Sunday -->
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/mark/ai_log_backups/backup.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/mark/ai_log_backups/backup.log</string>
</dict>
</plist>
```

## Key Commands

### See what's registered for your user:
```bash
# List all loaded jobs for current user
launchctl list

# Filter to find yours
launchctl list | grep -i backup
launchctl list | grep com.mark
```

### See the .plist files (job definitions):
```bash
# Your user agents live here
ls -la ~/Library/LaunchAgents/

# Read a specific one
cat ~/Library/LaunchAgents/com.mark.ai-backup.plist
```

### Register (load) a job:
```bash
# Load a plist (registers it with launchd)
launchctl load ~/Library/LaunchAgents/com.mark.ai-backup.plist

# On newer macOS (Ventura+), you may need:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mark.ai-backup.plist
```

### Unregister (unload) a job:
```bash
# Stop and unregister
launchctl unload ~/Library/LaunchAgents/com.mark.ai-backup.plist

# On newer macOS:
launchctl bootout gui/$(id -u)/com.mark.ai-backup
```

### Run a job immediately (for testing):
```bash
# Kick off the job now, don't wait for schedule
launchctl start com.mark.ai-backup
```

### Check job status:
```bash
# See if it's loaded and last exit status
launchctl list com.mark.ai-backup

# Output: PID  ExitStatus  Label
#         -    0           com.mark.ai-backup
# (- means not currently running, 0 means last run succeeded)
```

## Logging

### Your job's output:
Goes wherever you specify in StandardOutPath/StandardErrorPath.
If not specified, output is lost.

```bash
# View your backup log
cat ~/ai_log_backups/backup.log
tail -f ~/ai_log_backups/backup.log  # follow live
```

### launchd system logs:
```bash
# launchd's own logs (job start/stop, errors)
log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h

# Filter to your job
log show --predicate 'subsystem == "com.apple.xpc.launchd" AND composedMessage CONTAINS "com.mark"' --last 1h

# Simpler: look for errors
log show --predicate 'process == "launchd"' --last 1h | grep -i error
```

### Common log location for debugging:
```bash
# System log (catch-all)
/var/log/system.log

# Or use Console.app (GUI) and filter by process
```

## Separation: Management vs Workload

```
MANAGEMENT (the .plist)              WORKLOAD (your script)
─────────────────────────────────    ─────────────────────────────
~/Library/LaunchAgents/              ~/src/ai_shell_logging/
  com.mark.ai-backup.plist             backup_logs.sh

- Defines WHEN to run                - Defines WHAT to do
- Defines WHERE to log               - Does the actual work
- Lives in system location           - Lives in your project
- Loaded/unloaded via launchctl      - Edited freely without reload
```

**Key insight**: You can edit backup_logs.sh anytime without touching launchd.
The .plist just points to it. Only reload the .plist if you change the
schedule, label, or log paths.

## Troubleshooting

### Job not running?
```bash
# Is it loaded?
launchctl list | grep com.mark

# Check for syntax errors in plist
plutil -lint ~/Library/LaunchAgents/com.mark.ai-backup.plist

# Check launchd logs for errors
log show --predicate 'process == "launchd"' --last 30m | grep -i com.mark
```

### Permission issues?
```bash
# Script must be executable
chmod +x ~/src/ai_shell_logging/backup_logs.sh

# Log directory must exist
mkdir -p ~/ai_log_backups
```

### Job runs but fails?
```bash
# Check your job's log
cat ~/ai_log_backups/backup.log

# Run manually to see errors
~/src/ai_shell_logging/backup_logs.sh
```

## Quick Reference

| Task | Command |
|------|---------|
| List my jobs | `launchctl list \| grep com.mark` |
| See job files | `ls ~/Library/LaunchAgents/` |
| Load a job | `launchctl load ~/Library/LaunchAgents/FILE.plist` |
| Unload a job | `launchctl unload ~/Library/LaunchAgents/FILE.plist` |
| Run now | `launchctl start LABEL` |
| Check status | `launchctl list LABEL` |
| Validate plist | `plutil -lint FILE.plist` |
| View logs | `log show --predicate 'process == "launchd"' --last 1h` |
