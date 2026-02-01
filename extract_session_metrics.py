#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
extract_session_metrics.py - Extract Claude session metrics to CSV

Reads Claude Code's native JSONL logs and extracts per-session metrics
for analysis in spreadsheets or pandas. The CSV is the primary artifact.

Usage:
    ./extract_session_metrics.py                  # Writes claude_session_metrics.csv
    ./extract_session_metrics.py -o report.csv    # Custom output filename
    ./extract_session_metrics.py --stdout         # Output to terminal
    ./extract_session_metrics.py --json           # JSON format
    ./extract_session_metrics.py -q               # Quiet (no summary)

Output:
    Creates a CSV file with per-session metrics including tool usage,
    message counts, error rates, and token/byte statistics.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def find_claude_sessions(claude_dir: Path = None) -> list:
    """Find all Claude Code session files."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"
    
    if not claude_dir.exists():
        return []
    
    sessions = []
    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            if jsonl.name == "sessions-index.json":
                continue
            sessions.append({
                "path": jsonl,
                "project": project_dir.name
            })
    
    return sessions


def extract_metrics(jsonl_path: Path) -> dict:
    """Extract metrics from a single session JSONL."""
    metrics = {
        "session_file": jsonl_path.name,
        "project": jsonl_path.parent.name,
        "user_messages": 0,
        "assistant_messages": 0,
        "total_messages": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "tools_used": defaultdict(int),
        "bytes_to_llm": 0,
        "bytes_from_llm": 0,
        "files_read": set(),
        "files_written": set(),
        "files_edited": set(),
        "bash_commands": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "first_prompt": "",
    }
    
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                msg_type = entry.get("type")
                timestamp = entry.get("timestamp")
                
                if timestamp:
                    if metrics["first_timestamp"] is None:
                        metrics["first_timestamp"] = timestamp
                    metrics["last_timestamp"] = timestamp
                
                if msg_type == "user":
                    metrics["user_messages"] += 1
                    metrics["total_messages"] += 1
                    
                    if not metrics["first_prompt"]:
                        msg = entry.get("message", {})
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            metrics["first_prompt"] = content[:100]
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, str):
                                    metrics["first_prompt"] = item[:100]
                                    break
                                elif isinstance(item, dict) and item.get("type") == "text":
                                    metrics["first_prompt"] = item.get("text", "")[:100]
                                    break
                
                elif msg_type == "assistant":
                    metrics["assistant_messages"] += 1
                    metrics["total_messages"] += 1
                
                msg = entry.get("message", {})
                content = msg.get("content", [])
                
                if isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        
                        if item.get("type") == "tool_use":
                            metrics["tool_calls"] += 1
                            tool_name = item.get("name", "unknown")
                            metrics["tools_used"][tool_name] += 1
                            
                            inp = item.get("input", {})
                            metrics["bytes_from_llm"] += len(json.dumps(inp))
                            
                            if tool_name == "Read":
                                path = inp.get("file_path", "")
                                if path:
                                    metrics["files_read"].add(path)
                            elif tool_name == "Write":
                                path = inp.get("file_path", "")
                                if path:
                                    metrics["files_written"].add(path)
                            elif tool_name == "Edit":
                                path = inp.get("file_path", "")
                                if path:
                                    metrics["files_edited"].add(path)
                            elif tool_name == "Bash":
                                metrics["bash_commands"] += 1
                        
                        elif item.get("type") == "tool_result":
                            result = item.get("content", "")
                            if isinstance(result, str):
                                metrics["bytes_to_llm"] += len(result)
                            else:
                                metrics["bytes_to_llm"] += len(json.dumps(result))
                            
                            if item.get("is_error"):
                                metrics["tool_errors"] += 1
    
    except Exception as e:
        metrics["error"] = str(e)
    
    return metrics


def metrics_to_row(metrics: dict) -> dict:
    """Convert metrics dict to flat CSV row."""
    duration_minutes = None
    if metrics["first_timestamp"] and metrics["last_timestamp"]:
        try:
            first = datetime.fromisoformat(metrics["first_timestamp"].replace("Z", "+00:00"))
            last = datetime.fromisoformat(metrics["last_timestamp"].replace("Z", "+00:00"))
            duration_minutes = (last - first).total_seconds() / 60
        except:
            pass
    
    tools_used = metrics["tools_used"]
    top_tools = sorted(tools_used.items(), key=lambda x: -x[1])[:5]
    top_tools_str = ", ".join(f"{t}:{c}" for t, c in top_tools)
    
    return {
        "session_file": metrics["session_file"],
        "project": metrics["project"],
        "date": metrics["first_timestamp"][:10] if metrics["first_timestamp"] else "",
        "duration_min": round(duration_minutes, 1) if duration_minutes else "",
        "user_msgs": metrics["user_messages"],
        "assistant_msgs": metrics["assistant_messages"],
        "total_msgs": metrics["total_messages"],
        "tool_calls": metrics["tool_calls"],
        "tool_errors": metrics["tool_errors"],
        "error_rate": round(metrics["tool_errors"] / metrics["tool_calls"] * 100, 1) if metrics["tool_calls"] > 0 else 0,
        "bytes_to_llm": metrics["bytes_to_llm"],
        "bytes_from_llm": metrics["bytes_from_llm"],
        "files_read": len(metrics["files_read"]),
        "files_written": len(metrics["files_written"]),
        "files_edited": len(metrics["files_edited"]),
        "bash_cmds": metrics["bash_commands"],
        "top_tools": top_tools_str,
        "first_prompt": metrics["first_prompt"].replace("\n", " ")[:80],
    }


def print_summary(rows: list) -> None:
    """Print a summary of the extracted metrics."""
    if not rows:
        return

    total_sessions = len(rows)
    total_tool_calls = sum(r["tool_calls"] for r in rows)
    total_errors = sum(r["tool_errors"] for r in rows)
    total_user_msgs = sum(r["user_msgs"] for r in rows)
    total_bytes_to = sum(r["bytes_to_llm"] for r in rows)
    total_bytes_from = sum(r["bytes_from_llm"] for r in rows)

    # Find date range
    dates = [r["date"] for r in rows if r["date"]]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "unknown"

    # Unique projects
    projects = set(r["project"] for r in rows)

    print("\n" + "=" * 60)
    print("CLAUDE SESSION METRICS SUMMARY")
    print("=" * 60)
    print(f"Sessions analyzed:    {total_sessions}")
    print(f"Date range:           {date_range}")
    print(f"Projects:             {len(projects)}")
    print(f"Total user messages:  {total_user_msgs}")
    print(f"Total tool calls:     {total_tool_calls}")
    print(f"Total tool errors:    {total_errors} ({total_errors/total_tool_calls*100:.1f}%)" if total_tool_calls else "Total tool errors:    0")
    print(f"Data to LLM:          {total_bytes_to:,} bytes ({total_bytes_to/1024/1024:.1f} MB)")
    print(f"Data from LLM:        {total_bytes_from:,} bytes ({total_bytes_from/1024/1024:.1f} MB)")
    print("=" * 60 + "\n")


def main():
    import argparse

    default_output = Path("claude_session_metrics.csv")

    parser = argparse.ArgumentParser(description="Extract Claude session metrics to CSV")
    parser.add_argument("-o", "--output", type=Path, default=default_output,
                        help=f"Output file (default: {default_output})")
    parser.add_argument("--stdout", action="store_true", help="Write to stdout instead of file")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of CSV")
    parser.add_argument("--dir", type=Path, help="Claude projects dir (default: ~/.claude/projects)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress summary output")
    args = parser.parse_args()

    sessions = find_claude_sessions(args.dir)

    if not sessions:
        print("No Claude sessions found.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(sessions)} sessions...", file=sys.stderr)

    rows = []
    for session in sessions:
        metrics = extract_metrics(session["path"])
        row = metrics_to_row(metrics)
        rows.append(row)

    rows.sort(key=lambda x: x["date"], reverse=True)

    fieldnames = [
        "date", "duration_min", "project", "user_msgs", "assistant_msgs", "total_msgs",
        "tool_calls", "tool_errors", "error_rate", "bytes_to_llm", "bytes_from_llm",
        "files_read", "files_written", "files_edited", "bash_cmds",
        "top_tools", "first_prompt", "session_file"
    ]

    if args.json:
        output = json.dumps(rows, indent=2)
        if args.stdout:
            print(output)
        else:
            output_path = args.output.with_suffix(".json")
            output_path.write_text(output)
            print(f"\n>>> CSV ARTIFACT: {output_path.absolute()}", file=sys.stderr)
    else:
        if args.stdout:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        else:
            with open(args.output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\n>>> CSV ARTIFACT: {args.output.absolute()}", file=sys.stderr)

    if not args.quiet and not args.stdout:
        print_summary(rows)


if __name__ == "__main__":
    main()
