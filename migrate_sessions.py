#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
migrate_sessions.py - Migrate legacy session files to JSONL format

Converts old .json files (single-file format) to Claude-compatible JSONL.

Usage:
    ./migrate_sessions.py ollama              # Migrate ollama sessions
    ./migrate_sessions.py ollama --dry-run    # Preview without changes
    ./migrate_sessions.py --all               # Migrate all apps
    ./migrate_sessions.py --status            # Show migration status
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from session_converter import SessionConverter, parse_timestamp_from_filename
from session_index import SessionIndex


BASE_DIR = Path.home() / "ai_shell_logs"
# Note: claude here refers to terminal captures from `claude` CLI wrapper,
# NOT Claude Code's native JSONL in ~/.claude/projects/
APPS = ["ollama", "gemini", "claude"]


def get_legacy_files(app: str) -> List[Path]:
    """Find legacy .json files that need migration."""
    app_dir = BASE_DIR / app
    legacy_files = []

    # Look for .json files in app root (not in sessions/ or legacy/)
    for json_file in app_dir.glob("*.json"):
        if json_file.name == "sessions-index.json":
            continue
        legacy_files.append(json_file)

    return sorted(legacy_files)


def get_legacy_logs(app: str) -> List[Path]:
    """Find raw .log files that haven't been converted to JSONL."""
    app_dir = BASE_DIR / app
    sessions_dir = app_dir / "sessions"

    # Get existing session source files
    existing_sources = set()
    if sessions_dir.exists():
        index = SessionIndex(app)
        for entry in index.entries:
            existing_sources.add(Path(entry.sourceFile).name)

    # Find .log files not yet converted
    unconverted = []
    for log_file in app_dir.glob("*.log"):
        if log_file.name not in existing_sources:
            unconverted.append(log_file)

    return sorted(unconverted)


def migrate_json_file(json_file: Path, app: str, dry_run: bool = False) -> Optional[str]:
    """
    Migrate a legacy .json file to JSONL format.

    Returns the new session ID on success, None on failure.
    """
    try:
        with open(json_file) as f:
            data = json.load(f)

        messages = data.get("messages", [])
        if not messages:
            print(f"  Skipping {json_file.name}: no messages")
            return None

        # Parse timestamp from filename
        start_time = parse_timestamp_from_filename(json_file.name)

        # Create converter
        converter = SessionConverter(
            app=app,
            source_file=json_file,
            start_time=start_time
        )

        # Add messages
        for msg in messages:
            converter.add_message(msg.get("role", "user"), msg.get("content", ""))

        if dry_run:
            print(f"  Would migrate: {json_file.name}")
            print(f"    Session ID: {converter.session_id}")
            print(f"    Messages: {converter.message_count}")
            return converter.session_id

        # Write JSONL
        sessions_dir = BASE_DIR / app / "sessions"
        output_path = sessions_dir / f"{converter.session_id}.jsonl"
        converter.write_jsonl(output_path)

        # Update index
        index = SessionIndex(app)
        index.add_session(
            session_id=converter.session_id,
            jsonl_path=output_path,
            source_file=json_file,
            first_prompt=converter.first_prompt,
            message_count=converter.message_count
        )

        # Move legacy file
        legacy_dir = BASE_DIR / app / "legacy"
        legacy_dir.mkdir(exist_ok=True)
        json_file.rename(legacy_dir / json_file.name)

        print(f"  Migrated: {json_file.name} -> {converter.session_id[:8]}...")
        return converter.session_id

    except Exception as e:
        print(f"  Error migrating {json_file.name}: {e}")
        return None


def migrate_log_file(log_file: Path, app: str, dry_run: bool = False) -> Optional[str]:
    """
    Convert a raw .log file to JSONL format.

    Returns the new session ID on success, None on failure.
    """
    try:
        # Import ai_export for rendering
        from ai_export import render_log, parse_messages

        # Render and parse
        rendered = render_log(log_file)
        messages = parse_messages(rendered)

        if not messages:
            print(f"  Skipping {log_file.name}: no messages found")
            return None

        # Parse timestamp from filename
        start_time = parse_timestamp_from_filename(log_file.name)

        # Create converter
        converter = SessionConverter(
            app=app,
            source_file=log_file,
            start_time=start_time
        )

        # Add messages
        for msg in messages:
            converter.add_message(msg["role"], msg["content"])

        if dry_run:
            print(f"  Would convert: {log_file.name}")
            print(f"    Session ID: {converter.session_id}")
            print(f"    Messages: {converter.message_count}")
            return converter.session_id

        # Write JSONL
        sessions_dir = BASE_DIR / app / "sessions"
        output_path = sessions_dir / f"{converter.session_id}.jsonl"
        converter.write_jsonl(output_path)

        # Update index
        index = SessionIndex(app)
        index.add_session(
            session_id=converter.session_id,
            jsonl_path=output_path,
            source_file=log_file,
            first_prompt=converter.first_prompt,
            message_count=converter.message_count
        )

        # Optionally archive raw log
        raw_dir = BASE_DIR / app / "raw"
        raw_dir.mkdir(exist_ok=True)
        shutil.copy2(log_file, raw_dir / log_file.name)
        log_file.unlink()

        print(f"  Converted: {log_file.name} -> {converter.session_id[:8]}...")
        return converter.session_id

    except Exception as e:
        print(f"  Error converting {log_file.name}: {e}")
        return None


def migrate_app(app: str, dry_run: bool = False) -> Dict[str, int]:
    """
    Migrate all legacy files for an app.

    Returns dict with counts: migrated_json, converted_logs, errors
    """
    print(f"\nMigrating {app}...")

    results = {"migrated_json": 0, "converted_logs": 0, "errors": 0, "skipped": 0}

    # Migrate legacy .json files
    json_files = get_legacy_files(app)
    if json_files:
        print(f"\n  Found {len(json_files)} legacy .json files")
        for json_file in json_files:
            session_id = migrate_json_file(json_file, app, dry_run)
            if session_id:
                results["migrated_json"] += 1
            else:
                results["errors"] += 1

    # Convert raw .log files
    log_files = get_legacy_logs(app)
    if log_files:
        print(f"\n  Found {len(log_files)} unconverted .log files")
        for log_file in log_files:
            session_id = migrate_log_file(log_file, app, dry_run)
            if session_id:
                results["converted_logs"] += 1
            else:
                results["errors"] += 1

    if not json_files and not log_files:
        print("  No files to migrate")

    return results


def show_status():
    """Show migration status for all apps."""
    print("Migration Status")
    print("=" * 60)

    for app in APPS:
        app_dir = BASE_DIR / app
        if not app_dir.exists():
            continue

        print(f"\n{app}:")

        # Count legacy files
        json_files = get_legacy_files(app)
        log_files = get_legacy_logs(app)

        # Count migrated
        sessions_dir = app_dir / "sessions"
        jsonl_count = len(list(sessions_dir.glob("*.jsonl"))) if sessions_dir.exists() else 0

        # Count archived
        legacy_dir = app_dir / "legacy"
        legacy_count = len(list(legacy_dir.glob("*.json"))) if legacy_dir.exists() else 0
        raw_dir = app_dir / "raw"
        raw_count = len(list(raw_dir.glob("*.log"))) if raw_dir.exists() else 0

        print(f"  JSONL sessions:      {jsonl_count}")
        print(f"  Pending .json:       {len(json_files)}")
        print(f"  Pending .log:        {len(log_files)}")
        print(f"  Archived (legacy/):  {legacy_count}")
        print(f"  Archived (raw/):     {raw_count}")

        # Index status
        index = SessionIndex(app)
        print(f"  Index entries:       {len(index)}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate legacy session files to JSONL format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    ./migrate_sessions.py ollama              # Migrate ollama sessions
    ./migrate_sessions.py ollama --dry-run    # Preview without changes
    ./migrate_sessions.py --all               # Migrate all apps
    ./migrate_sessions.py --status            # Show migration status
        """
    )
    parser.add_argument("app", nargs="?", choices=APPS,
                        help="App to migrate")
    parser.add_argument("--all", action="store_true",
                        help="Migrate all apps")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without migrating")
    parser.add_argument("--status", action="store_true",
                        help="Show migration status")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if not args.app and not args.all:
        parser.print_help()
        return

    apps_to_migrate = APPS if args.all else [args.app]

    total_results = {"migrated_json": 0, "converted_logs": 0, "errors": 0}

    for app in apps_to_migrate:
        results = migrate_app(app, args.dry_run)
        for key in total_results:
            total_results[key] += results.get(key, 0)

    print("\n" + "=" * 60)
    if args.dry_run:
        print("DRY RUN - No changes made")
    print(f"JSON files migrated: {total_results['migrated_json']}")
    print(f"Log files converted: {total_results['converted_logs']}")
    print(f"Errors: {total_results['errors']}")


if __name__ == "__main__":
    main()
