#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
schema_analyzer.py - Analyze the schema/namespace of Claude Code JSONL logs

Discovers all keys, types, and structures present in the logs to understand
what data is available for extraction and analysis.

Usage:
    schema_analyzer.py                    # Analyze all sessions
    schema_analyzer.py <jsonl_file>       # Analyze specific file
    schema_analyzer.py --deep             # Show nested structure details
"""

import sys
import json
from pathlib import Path
from collections import defaultdict


def analyze_schema(jsonl_paths: list, deep: bool = False) -> dict:
    """Analyze schema across all provided JSONL files."""

    top_keys = defaultdict(int)
    message_keys = defaultdict(int)
    content_types = defaultdict(int)
    entry_types = defaultdict(int)
    usage_keys = defaultdict(int)
    tool_names = defaultdict(int)

    # For deep analysis
    tool_input_keys = defaultdict(lambda: defaultdict(int))
    nested_structures = defaultdict(set)

    entry_count = 0

    for jsonl_path in jsonl_paths:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    entry_count += 1
                except json.JSONDecodeError:
                    continue

                # Entry type
                entry_types[obj.get('type', 'no-type')] += 1

                # Top-level keys
                for k in obj.keys():
                    top_keys[k] += 1
                    if deep and isinstance(obj[k], dict):
                        nested_structures[f"top.{k}"].update(obj[k].keys())

                # Message keys
                msg = obj.get('message', {})
                for k in msg.keys():
                    message_keys[k] += 1

                # Usage keys (token tracking)
                usage = msg.get('usage', {})
                for k in usage.keys():
                    usage_keys[k] += 1

                # Content analysis
                content = msg.get('content', [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            item_type = item.get('type', 'unknown')
                            content_types[item_type] += 1

                            # Tool tracking
                            if item_type == 'tool_use':
                                tool_name = item.get('name', 'unknown')
                                tool_names[tool_name] += 1
                                if deep:
                                    inp = item.get('input', {})
                                    if isinstance(inp, dict):
                                        for k in inp.keys():
                                            tool_input_keys[tool_name][k] += 1

    result = {
        "entry_count": entry_count,
        "entry_types": dict(entry_types),
        "top_level_keys": dict(top_keys),
        "message_keys": dict(message_keys),
        "usage_keys": dict(usage_keys),
        "content_types": dict(content_types),
        "tool_names": dict(tool_names),
    }

    if deep:
        result["tool_input_keys"] = {k: dict(v) for k, v in tool_input_keys.items()}
        result["nested_structures"] = {k: list(v) for k, v in nested_structures.items()}

    return result


def find_all_sessions(claude_dir: Path = None) -> list:
    """Find all session JSONL files."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"

    sessions = []
    if not claude_dir.exists():
        return sessions

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            sessions.append(jsonl_file)

    return sessions


def print_report(schema: dict, deep: bool = False):
    """Print human-readable schema report."""
    print("=" * 70)
    print("CLAUDE CODE LOG SCHEMA ANALYSIS")
    print("=" * 70)

    print(f"\nTotal entries analyzed: {schema['entry_count']:,}")

    print(f"\n{'='*70}")
    print("ENTRY TYPES")
    print("=" * 70)
    for k, v in sorted(schema['entry_types'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")

    print(f"\n{'='*70}")
    print("TOP-LEVEL KEYS")
    print("=" * 70)
    for k, v in sorted(schema['top_level_keys'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")

    print(f"\n{'='*70}")
    print("MESSAGE KEYS (inside 'message' object)")
    print("=" * 70)
    for k, v in sorted(schema['message_keys'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")

    print(f"\n{'='*70}")
    print("USAGE KEYS (token tracking)")
    print("=" * 70)
    for k, v in sorted(schema['usage_keys'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")

    print(f"\n{'='*70}")
    print("CONTENT TYPES (inside message.content[])")
    print("=" * 70)
    for k, v in sorted(schema['content_types'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")

    print(f"\n{'='*70}")
    print("TOOL NAMES")
    print("=" * 70)
    for k, v in sorted(schema['tool_names'].items(), key=lambda x: -x[1]):
        print(f"  {k}: {v:,}")

    if deep and 'tool_input_keys' in schema:
        print(f"\n{'='*70}")
        print("TOOL INPUT PARAMETERS (per tool)")
        print("=" * 70)
        for tool, params in sorted(schema['tool_input_keys'].items()):
            print(f"\n  {tool}:")
            for k, v in sorted(params.items(), key=lambda x: -x[1]):
                print(f"    {k}: {v:,}")

    if deep and 'nested_structures' in schema:
        print(f"\n{'='*70}")
        print("NESTED STRUCTURE KEYS")
        print("=" * 70)
        for parent, keys in sorted(schema['nested_structures'].items()):
            print(f"\n  {parent}:")
            for k in sorted(keys):
                print(f"    - {k}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze Claude Code log schema")
    parser.add_argument("file", nargs="?", type=Path, help="Specific JSONL file to analyze")
    parser.add_argument("--deep", action="store_true", help="Show nested structure details")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.file:
        sessions = [args.file]
    else:
        sessions = find_all_sessions()

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(sessions)} session files...", file=sys.stderr)
    schema = analyze_schema(sessions, deep=args.deep)

    if args.json:
        print(json.dumps(schema, indent=2))
    else:
        print_report(schema, deep=args.deep)


if __name__ == "__main__":
    main()
