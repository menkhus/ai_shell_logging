#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
cwd_drift_check.py - Detect working directory drift in Claude Code sessions.

Diagnoses the scenario where a user:
1. Creates a new directory
2. cd's into it within the same shell
3. Continues working with Claude Code

This can cause Claude Code to have a stale sense of cwd.

Usage:
    python cwd_drift_check.py              # Check all sessions
    python cwd_drift_check.py --recent 5   # Check last 5 sessions per project
    python cwd_drift_check.py --verbose    # Show all cwd values per session
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime


CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def extract_cwds_from_session(jsonl_path: Path) -> list[dict]:
    """Extract all cwd values from a session file with timestamps."""
    cwds = []
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if "cwd" in record:
                        cwds.append({
                            "cwd": record["cwd"],
                            "timestamp": record.get("timestamp", ""),
                            "type": record.get("type", "unknown"),
                            "uuid": record.get("uuid", "")[:8]
                        })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"  Error reading {jsonl_path}: {e}", file=sys.stderr)
    return cwds


def project_dir_to_path(dir_name: str) -> str:
    """Convert project directory name back to path."""
    # -Users-mark-src-foo -> /Users/mark/src/foo
    return "/" + dir_name.lstrip("-").replace("-", "/")


def check_session(jsonl_path: Path, verbose: bool = False) -> dict:
    """Check a single session for cwd drift."""
    cwds = extract_cwds_from_session(jsonl_path)
    if not cwds:
        return {"status": "empty", "file": jsonl_path.name}

    unique_cwds = list(set(c["cwd"] for c in cwds))

    result = {
        "file": jsonl_path.name,
        "message_count": len(cwds),
        "unique_cwds": unique_cwds,
        "status": "ok" if len(unique_cwds) == 1 else "DRIFT"
    }

    if verbose:
        result["cwd_timeline"] = cwds

    if len(unique_cwds) > 1:
        # Find where the drift occurred
        prev_cwd = None
        transitions = []
        for c in cwds:
            if prev_cwd and c["cwd"] != prev_cwd:
                transitions.append({
                    "from": prev_cwd,
                    "to": c["cwd"],
                    "at": c["timestamp"],
                    "type": c["type"]
                })
            prev_cwd = c["cwd"]
        result["transitions"] = transitions

    return result


def check_project_dir_mismatch(project_dir: Path, session_cwd: str) -> dict | None:
    """Check if session cwd is outside the project directory tree.

    Returns mismatch info if cwd is completely outside the project tree,
    None if it's within the project (including subdirs).
    """
    # The project dir name uses dashes, but actual path uses underscores/dashes
    # e.g., -Users-mark-src-ai-shell-logging stores /Users/mark/src/ai_shell_logging

    # Get the first cwd from session as the "project root"
    # A session starting at /foo/bar should store in -foo-bar
    # Check if current cwd shares no common prefix with project expectation

    dir_parts = project_dir.name.lstrip("-").split("-")
    cwd_parts = session_cwd.strip("/").split("/")

    # Find where paths diverge
    # The project dir will be: Users-mark-src-foo-bar
    # The cwd could be: /Users/mark/src/foo_bar or /Users/mark/src/foo_bar/subdir

    # Convert dir_parts back to likely path prefixes
    # This is tricky because foo-bar could be foo_bar or foo/bar
    # Use heuristic: if cwd is completely different project, flag it

    # Simple check: is this a sibling directory (different project entirely)?
    if len(cwd_parts) >= 4:  # /Users/mark/src/project
        cwd_project = cwd_parts[3] if len(cwd_parts) > 3 else ""
        # Reconstruct what project name should be from dir
        # -Users-mark-src-foo-bar -> last parts after "src" joined
        try:
            src_idx = dir_parts.index("src")
            dir_project = "-".join(dir_parts[src_idx+1:])
        except ValueError:
            return None  # Can't determine

        # Normalize for comparison (underscore = dash)
        cwd_project_norm = cwd_project.replace("_", "-").replace(".", "-").lower()
        dir_project_norm = dir_project.lower()

        # Check if it's the same project (accounting for subdirs in cwd)
        if cwd_project_norm == dir_project_norm:
            return None  # Same project
        if dir_project_norm.startswith(cwd_project_norm):
            return None  # cwd is parent of project
        if cwd_project_norm.startswith(dir_project_norm.split("-")[0]):
            return None  # Likely same project with different naming

        # This is a different project
        return {
            "project_dir": project_dir.name,
            "cwd_project": cwd_project,
            "dir_project": dir_project
        }

    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check for cwd drift in Claude sessions")
    parser.add_argument("--recent", type=int, default=0, help="Only check N most recent sessions per project")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full cwd timeline")
    parser.add_argument("--project", type=str, help="Only check specific project (substring match)")
    args = parser.parse_args()

    if not CLAUDE_PROJECTS.exists():
        print(f"Claude projects directory not found: {CLAUDE_PROJECTS}")
        sys.exit(1)

    drift_found = []
    mismatch_found = []
    sessions_checked = 0

    for project_dir in sorted(CLAUDE_PROJECTS.iterdir()):
        if not project_dir.is_dir():
            continue
        if args.project and args.project not in project_dir.name:
            continue

        jsonl_files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

        if args.recent:
            jsonl_files = jsonl_files[:args.recent]

        for jsonl_path in jsonl_files:
            sessions_checked += 1
            result = check_session(jsonl_path, verbose=args.verbose)

            if result["status"] == "DRIFT":
                drift_found.append({
                    "project": project_dir.name,
                    **result
                })

            # Check if session cwd is outside the project tree
            if result.get("unique_cwds"):
                for cwd in result["unique_cwds"]:
                    mismatch = check_project_dir_mismatch(project_dir, cwd)
                    if mismatch:
                        mismatch_found.append({
                            **mismatch,
                            "actual_cwd": cwd,
                            "session": jsonl_path.name
                        })

    # Report
    print(f"Sessions checked: {sessions_checked}")
    print()

    if drift_found:
        print(f"=== CWD DRIFT DETECTED ({len(drift_found)} sessions) ===")
        for d in drift_found:
            print(f"\nProject: {d['project']}")
            print(f"Session: {d['file']}")
            print(f"CWDs found: {d['unique_cwds']}")
            if "transitions" in d:
                print("Transitions:")
                for t in d["transitions"]:
                    print(f"  {t['at']}: {t['from']} -> {t['to']} (during {t['type']})")
            if args.verbose and "cwd_timeline" in d:
                print("Full timeline:")
                for c in d["cwd_timeline"]:
                    print(f"  {c['timestamp']} [{c['type']}] {c['cwd']}")
    else:
        print("No cwd drift detected within sessions.")

    print()

    if mismatch_found:
        print(f"=== CROSS-PROJECT SESSIONS ({len(mismatch_found)} cases) ===")
        print("(Sessions where you cd'd to a completely different project)")
        for m in mismatch_found:
            print(f"\nSession stored in: {m['project_dir']}")
            print(f"But worked in:     {m['actual_cwd']}")
            print(f"Session file:      {m['session']}")
    else:
        print("No cross-project sessions detected.")


if __name__ == "__main__":
    main()
