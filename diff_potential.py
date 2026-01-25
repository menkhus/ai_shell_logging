#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
diff_potential.py - Study potential savings from a diff/cache layer

Analyzes session logs to compute:
- What was actually transferred
- What could have been transferred with caching
- What could have been transferred with diffing

This is research tooling, not the mechanism itself.
"""

import json
import sys
import difflib
from pathlib import Path
from collections import defaultdict


def extract_file_reads(jsonl_path: Path) -> list:
    """Extract all Read tool calls with their results in order."""
    reads = []

    with open(jsonl_path) as f:
        tool_calls = {}  # id -> call info

        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = entry.get("message", {})
            content = msg.get("content", [])

            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue

                    if item.get("type") == "tool_use" and item.get("name") == "Read":
                        tool_id = item.get("id")
                        tool_calls[tool_id] = {
                            "path": item.get("input", {}).get("file_path"),
                            "timestamp": entry.get("timestamp"),
                            "result": None
                        }

                    elif item.get("type") == "tool_result":
                        tool_id = item.get("tool_use_id")
                        if tool_id in tool_calls:
                            tool_calls[tool_id]["result"] = item.get("content", "")
                            if not item.get("is_error"):
                                reads.append(tool_calls[tool_id])

    return reads


def analyze_potential(reads: list) -> dict:
    """Analyze potential savings from caching and diffing."""

    # Track state per file
    file_states = {}  # path -> last content seen

    actual_bytes = 0
    with_cache_bytes = 0
    with_diff_bytes = 0

    details = []

    for read in reads:
        path = read["path"]
        content = read["result"]
        if not isinstance(content, str):
            continue

        content_bytes = len(content.encode('utf-8'))
        actual_bytes += content_bytes

        if path not in file_states:
            # First read - no savings possible
            file_states[path] = content
            with_cache_bytes += content_bytes
            with_diff_bytes += content_bytes
            details.append({
                "path": path,
                "action": "first_read",
                "actual": content_bytes,
                "with_cache": content_bytes,
                "with_diff": content_bytes
            })
        else:
            prev_content = file_states[path]

            if content == prev_content:
                # No change - cache returns "unchanged" signal
                cache_cost = 20  # ~20 bytes for "no change" response
                diff_cost = 20
                details.append({
                    "path": path,
                    "action": "unchanged",
                    "actual": content_bytes,
                    "with_cache": cache_cost,
                    "with_diff": cache_cost,
                    "savings": content_bytes - cache_cost
                })
            else:
                # Content changed - cache misses, diff wins
                diff = list(difflib.unified_diff(
                    prev_content.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    lineterm=''
                ))
                diff_text = ''.join(diff)
                diff_bytes = len(diff_text.encode('utf-8'))

                cache_cost = content_bytes  # cache miss, full content
                diff_cost = min(diff_bytes, content_bytes)  # diff or full, whichever smaller

                details.append({
                    "path": path,
                    "action": "changed",
                    "actual": content_bytes,
                    "with_cache": cache_cost,
                    "with_diff": diff_cost,
                    "diff_size": diff_bytes,
                    "savings": content_bytes - diff_cost
                })

            with_cache_bytes += cache_cost
            with_diff_bytes += diff_cost
            file_states[path] = content

    return {
        "actual_bytes": actual_bytes,
        "with_cache_bytes": with_cache_bytes,
        "with_diff_bytes": with_diff_bytes,
        "cache_savings": actual_bytes - with_cache_bytes,
        "diff_savings": actual_bytes - with_diff_bytes,
        "cache_savings_pct": round(100 * (actual_bytes - with_cache_bytes) / actual_bytes, 1) if actual_bytes else 0,
        "diff_savings_pct": round(100 * (actual_bytes - with_diff_bytes) / actual_bytes, 1) if actual_bytes else 0,
        "read_count": len(reads),
        "unique_files": len(file_states),
        "details": details
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: diff_potential.py <session.jsonl> [--details]", file=sys.stderr)
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])
    show_details = "--details" in sys.argv

    reads = extract_file_reads(jsonl_path)
    analysis = analyze_potential(reads)

    print("=" * 60)
    print("DIFF/CACHE POTENTIAL ANALYSIS")
    print("=" * 60)
    print(f"\nFile reads: {analysis['read_count']} ({analysis['unique_files']} unique files)")
    print(f"\nActual bytes transferred:  {analysis['actual_bytes']:,}")
    print(f"With simple caching:       {analysis['with_cache_bytes']:,} (saves {analysis['cache_savings_pct']}%)")
    print(f"With diff layer:           {analysis['with_diff_bytes']:,} (saves {analysis['diff_savings_pct']}%)")
    print(f"\nPotential savings:")
    print(f"  Cache alone: {analysis['cache_savings']:,} bytes")
    print(f"  Diff layer:  {analysis['diff_savings']:,} bytes")

    if show_details:
        print("\n" + "-" * 60)
        print("DETAILS:")
        for d in analysis["details"]:
            action = d["action"]
            path = Path(d["path"]).name
            if action == "first_read":
                print(f"  {path}: first read ({d['actual']:,}b)")
            elif action == "unchanged":
                print(f"  {path}: unchanged - save {d['savings']:,}b")
            else:
                print(f"  {path}: changed - diff {d.get('diff_size', 0):,}b vs full {d['actual']:,}b")

    print("=" * 60)


if __name__ == "__main__":
    main()
