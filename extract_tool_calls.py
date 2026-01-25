#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
extract_tool_calls.py - Extract tool calls from Claude Code session JSONL

Usage:
    extract_tool_calls.py <session.jsonl>           # Summary view
    extract_tool_calls.py <session.jsonl> --json    # Full JSON
    extract_tool_calls.py <session.jsonl> --stats   # Efficiency metrics
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

def extract_tools(jsonl_path: Path):
    """Extract tool_use and tool_result pairs from session JSONL."""
    tool_calls = {}  # id -> {call, result}

    with open(jsonl_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Look for tool_use in message content
            msg = entry.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "tool_use":
                            tool_id = item.get("id")
                            tool_calls[tool_id] = {
                                "name": item.get("name"),
                                "input": item.get("input"),
                                "timestamp": entry.get("timestamp"),
                                "result": None
                            }
                        elif item.get("type") == "tool_result":
                            tool_id = item.get("tool_use_id")
                            if tool_id in tool_calls:
                                tool_calls[tool_id]["result"] = item.get("content")
                                tool_calls[tool_id]["is_error"] = item.get("is_error", False)

    return list(tool_calls.values())


def compute_stats(tools: list) -> dict:
    """Compute efficiency metrics from tool calls."""
    stats = {
        "total_calls": len(tools),
        "by_tool": defaultdict(int),
        "bytes_in": 0,  # data sent to LLM (results)
        "bytes_out": 0,  # data from LLM (inputs)
        "file_reads": defaultdict(list),  # path -> [result_sizes]
        "file_writes": set(),
        "file_edits": set(),
        "redundant_reads": [],  # files read more than once
        "read_then_edit": [],  # files read then edited (diff candidates)
    }

    for t in tools:
        name = t["name"]
        inp = t["input"] or {}
        result = t.get("result") or ""

        stats["by_tool"][name] += 1
        stats["bytes_out"] += len(json.dumps(inp))
        stats["bytes_in"] += len(result) if isinstance(result, str) else len(json.dumps(result))

        # Track file operations
        if name == "Read":
            path = inp.get("file_path", "")
            size = len(result) if isinstance(result, str) else 0
            stats["file_reads"][path].append(size)
        elif name == "Write":
            stats["file_writes"].add(inp.get("file_path", ""))
        elif name == "Edit":
            stats["file_edits"].add(inp.get("file_path", ""))

    # Find redundant reads
    for path, sizes in stats["file_reads"].items():
        if len(sizes) > 1:
            stats["redundant_reads"].append({
                "path": path,
                "read_count": len(sizes),
                "total_bytes": sum(sizes),
                "wasted_bytes": sum(sizes) - max(sizes)  # could have cached after first read
            })

    # Find read-then-edit patterns (diff candidates)
    read_paths = set(stats["file_reads"].keys())
    edited_paths = stats["file_edits"] | stats["file_writes"]
    for path in read_paths & edited_paths:
        sizes = stats["file_reads"][path]
        stats["read_then_edit"].append({
            "path": path,
            "bytes_read": sum(sizes),
            "read_count": len(sizes)
        })

    # Convert sets to lists for JSON
    stats["file_writes"] = list(stats["file_writes"])
    stats["file_edits"] = list(stats["file_edits"])
    stats["by_tool"] = dict(stats["by_tool"])
    stats["file_reads"] = {k: len(v) for k, v in stats["file_reads"].items()}

    return stats


def print_stats(stats: dict):
    """Print human-readable efficiency report."""
    print("=" * 60)
    print("EFFICIENCY METRICS")
    print("=" * 60)

    print(f"\nTotal tool calls: {stats['total_calls']}")
    print(f"Data to LLM:      {stats['bytes_in']:,} bytes")
    print(f"Data from LLM:    {stats['bytes_out']:,} bytes")

    print("\nTool usage:")
    for tool, count in sorted(stats["by_tool"].items(), key=lambda x: -x[1]):
        print(f"  {tool}: {count}")

    if stats["redundant_reads"]:
        print("\n⚠ REDUNDANT READS (same file read multiple times):")
        total_wasted = 0
        for r in sorted(stats["redundant_reads"], key=lambda x: -x["wasted_bytes"]):
            print(f"  {r['path']}")
            print(f"    reads: {r['read_count']}, total: {r['total_bytes']:,}b, wasted: {r['wasted_bytes']:,}b")
            total_wasted += r["wasted_bytes"]
        print(f"  Total wasted: {total_wasted:,} bytes")

    if stats["read_then_edit"]:
        print("\n→ READ-THEN-EDIT (diff candidates):")
        total_readable = 0
        for r in stats["read_then_edit"]:
            print(f"  {r['path']}")
            print(f"    read {r['bytes_read']:,}b across {r['read_count']} call(s)")
            total_readable += r["bytes_read"]
        print(f"  Total bytes that could be diffs: {total_readable:,}")

    print("=" * 60)

def main():
    if len(sys.argv) < 2:
        print("Usage: extract_tool_calls.py <session.jsonl> [--json|--stats]", file=sys.stderr)
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])
    as_json = "--json" in sys.argv
    show_stats = "--stats" in sys.argv

    tools = extract_tools(jsonl_path)

    if show_stats:
        stats = compute_stats(tools)
        print_stats(stats)
    elif as_json:
        print(json.dumps(tools, indent=2))
    else:
        for t in tools:
            name = t["name"]
            inp = t["input"]
            err = " [ERROR]" if t.get("is_error") else ""

            if name == "Bash":
                cmd = inp.get("command", "")[:80]
                print(f"Bash: {cmd}{err}")
            elif name == "Read":
                print(f"Read: {inp.get('file_path', '')}{err}")
            elif name == "Write":
                print(f"Write: {inp.get('file_path', '')}{err}")
            elif name == "Edit":
                print(f"Edit: {inp.get('file_path', '')}{err}")
            elif name == "Grep":
                print(f"Grep: {inp.get('pattern', '')} in {inp.get('path', '.')}{err}")
            elif name == "Glob":
                print(f"Glob: {inp.get('pattern', '')}{err}")
            else:
                print(f"{name}: {inp}{err}")

if __name__ == "__main__":
    main()
