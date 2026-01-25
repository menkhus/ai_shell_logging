#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
opportunity_study.py - Map the opportunity space for a local diff/cache layer

Analyzes all Claude Code sessions to characterize:
- Transit inefficiencies (redundant data transfer)
- Latency costs (round trips that could be avoided)
- Token waste (context consumed by repeated content)

This is research tooling for studying potential optimizations in
AI tool orchestration. The patterns identified here apply to any
agentic tool system, not just Claude Code.

Usage:
    opportunity_study.py                    # Analyze all sessions
    opportunity_study.py --project <path>   # Analyze specific project
    opportunity_study.py --json             # Output as JSON for further analysis
    opportunity_study.py --verbose          # Show per-session details
"""

import json
import sys
import difflib
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import hashlib


# Approximate token costs (conservative estimates)
CHARS_PER_TOKEN = 4  # rough average
COST_PER_1K_INPUT_TOKENS = 0.003  # varies by model/tier
COST_PER_1K_OUTPUT_TOKENS = 0.015


def find_all_sessions(claude_dir: Path = None) -> list:
    """Find all session JSONL files across all projects."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"

    sessions = []
    if not claude_dir.exists():
        return sessions

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            if jsonl_file.name == "sessions-index.json":
                continue
            sessions.append({
                "path": jsonl_file,
                "project": project_dir.name,
                "size": jsonl_file.stat().st_size
            })

    return sessions


def extract_session_data(jsonl_path: Path) -> dict:
    """Extract all relevant data from a session for analysis."""
    data = {
        "tool_calls": [],
        "token_usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "file_operations": [],
        "timestamps": [],
        "errors": 0
    }

    tool_calls = {}  # id -> call info

    with open(jsonl_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Extract token usage from assistant messages
            msg = entry.get("message", {})
            usage = msg.get("usage", {})
            if usage:
                data["token_usage"]["input"] += usage.get("input_tokens", 0)
                data["token_usage"]["output"] += usage.get("output_tokens", 0)
                data["token_usage"]["cache_read"] += usage.get("cache_read_input_tokens", 0)
                data["token_usage"]["cache_write"] += usage.get("cache_creation_input_tokens", 0)

            # Extract timestamps
            ts = entry.get("timestamp")
            if ts:
                data["timestamps"].append(ts)

            # Extract tool calls
            content = msg.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue

                    if item.get("type") == "tool_use":
                        tool_id = item.get("id")
                        tool_calls[tool_id] = {
                            "name": item.get("name"),
                            "input": item.get("input", {}),
                            "timestamp": entry.get("timestamp"),
                            "result": None,
                            "is_error": False
                        }

                    elif item.get("type") == "tool_result":
                        tool_id = item.get("tool_use_id")
                        if tool_id in tool_calls:
                            result = item.get("content", "")
                            tool_calls[tool_id]["result"] = result
                            tool_calls[tool_id]["is_error"] = item.get("is_error", False)
                            if item.get("is_error"):
                                data["errors"] += 1

    data["tool_calls"] = list(tool_calls.values())
    return data


def analyze_file_operations(tool_calls: list) -> dict:
    """Analyze file read/write patterns for inefficiencies."""
    analysis = {
        "reads": defaultdict(list),  # path -> [(content_hash, size, timestamp)]
        "writes": [],
        "edits": [],
        "total_read_bytes": 0,
        "total_write_bytes": 0,
        "redundant_bytes": 0,
        "diff_potential_bytes": 0,
        "unique_files_read": set(),
        "unique_files_written": set()
    }

    file_state = {}  # path -> last content

    for call in tool_calls:
        name = call.get("name")
        inp = call.get("input", {})
        result = call.get("result", "")

        if call.get("is_error"):
            continue

        if name == "Read":
            path = inp.get("file_path", "")
            if not path or not isinstance(result, str):
                continue

            content_hash = hashlib.md5(result.encode()).hexdigest()[:8]
            size = len(result.encode('utf-8'))

            analysis["reads"][path].append({
                "hash": content_hash,
                "size": size,
                "timestamp": call.get("timestamp")
            })
            analysis["total_read_bytes"] += size
            analysis["unique_files_read"].add(path)

            # Check for redundancy
            if path in file_state:
                prev_hash, prev_content = file_state[path]
                if content_hash == prev_hash:
                    # Exact same content - fully redundant
                    analysis["redundant_bytes"] += size
                else:
                    # Content changed - compute diff potential
                    diff = list(difflib.unified_diff(
                        prev_content.splitlines(keepends=True),
                        result.splitlines(keepends=True)
                    ))
                    diff_size = len(''.join(diff).encode('utf-8'))
                    if diff_size < size:
                        analysis["diff_potential_bytes"] += (size - diff_size)

            file_state[path] = (content_hash, result)

        elif name == "Write":
            path = inp.get("file_path", "")
            content = inp.get("content", "")
            size = len(content.encode('utf-8')) if content else 0
            analysis["writes"].append({"path": path, "size": size})
            analysis["total_write_bytes"] += size
            analysis["unique_files_written"].add(path)

        elif name == "Edit":
            path = inp.get("file_path", "")
            old = inp.get("old_string", "")
            new = inp.get("new_string", "")
            analysis["edits"].append({
                "path": path,
                "old_size": len(old.encode('utf-8')),
                "new_size": len(new.encode('utf-8'))
            })
            analysis["unique_files_written"].add(path)

    # Convert sets for JSON serialization
    analysis["unique_files_read"] = len(analysis["unique_files_read"])
    analysis["unique_files_written"] = len(analysis["unique_files_written"])
    analysis["total_reads"] = sum(len(v) for v in analysis["reads"].values())

    # Compute redundant read stats
    redundant_reads = 0
    for path, reads in analysis["reads"].items():
        if len(reads) > 1:
            redundant_reads += len(reads) - 1

    analysis["redundant_reads"] = redundant_reads
    analysis["reads"] = dict(analysis["reads"])  # Convert defaultdict

    return analysis


def analyze_bash_operations(tool_calls: list) -> dict:
    """Analyze bash command patterns."""
    analysis = {
        "total_commands": 0,
        "unique_commands": set(),
        "command_categories": defaultdict(int),
        "total_output_bytes": 0,
        "repeated_commands": []
    }

    command_history = defaultdict(list)  # command -> [outputs]

    for call in tool_calls:
        if call.get("name") != "Bash":
            continue

        inp = call.get("input", {})
        cmd = inp.get("command", "")
        result = call.get("result", "")

        if not cmd:
            continue

        analysis["total_commands"] += 1
        analysis["unique_commands"].add(cmd)

        # Categorize command
        first_word = cmd.split()[0] if cmd.split() else ""
        if first_word in ("ls", "find", "tree"):
            analysis["command_categories"]["filesystem"] += 1
        elif first_word in ("git", "gh"):
            analysis["command_categories"]["git"] += 1
        elif first_word in ("grep", "rg", "ag"):
            analysis["command_categories"]["search"] += 1
        elif first_word in ("cat", "head", "tail", "less"):
            analysis["command_categories"]["read"] += 1
        elif first_word in ("python", "python3", "node", "npm", "pip"):
            analysis["command_categories"]["runtime"] += 1
        else:
            analysis["command_categories"]["other"] += 1

        output_size = len(result.encode('utf-8')) if isinstance(result, str) else 0
        analysis["total_output_bytes"] += output_size

        # Track repeated commands
        command_history[cmd].append(output_size)

    # Find repeated commands
    for cmd, outputs in command_history.items():
        if len(outputs) > 1:
            analysis["repeated_commands"].append({
                "command": cmd[:80],
                "count": len(outputs),
                "total_bytes": sum(outputs)
            })

    analysis["unique_commands"] = len(analysis["unique_commands"])
    analysis["command_categories"] = dict(analysis["command_categories"])

    return analysis


def compute_aggregate_stats(sessions_data: list) -> dict:
    """Compute aggregate statistics across all sessions."""
    agg = {
        "session_count": len(sessions_data),
        "total_tool_calls": 0,
        "total_tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "total_bytes": {"read": 0, "write": 0, "bash_output": 0},
        "inefficiencies": {
            "redundant_read_bytes": 0,
            "diff_potential_bytes": 0,
            "repeated_bash_bytes": 0
        },
        "tool_usage": defaultdict(int),
        "errors": 0,
        "time_span_days": 0
    }

    all_timestamps = []

    for session in sessions_data:
        data = session.get("data", {})
        file_ops = session.get("file_analysis", {})
        bash_ops = session.get("bash_analysis", {})

        agg["total_tool_calls"] += len(data.get("tool_calls", []))
        agg["errors"] += data.get("errors", 0)

        # Tokens
        for key in agg["total_tokens"]:
            agg["total_tokens"][key] += data.get("token_usage", {}).get(key, 0)

        # Bytes
        agg["total_bytes"]["read"] += file_ops.get("total_read_bytes", 0)
        agg["total_bytes"]["write"] += file_ops.get("total_write_bytes", 0)
        agg["total_bytes"]["bash_output"] += bash_ops.get("total_output_bytes", 0)

        # Inefficiencies
        agg["inefficiencies"]["redundant_read_bytes"] += file_ops.get("redundant_bytes", 0)
        agg["inefficiencies"]["diff_potential_bytes"] += file_ops.get("diff_potential_bytes", 0)

        for cmd in bash_ops.get("repeated_commands", []):
            if cmd["count"] > 1:
                # Estimate: all but first execution could be cached
                agg["inefficiencies"]["repeated_bash_bytes"] += cmd["total_bytes"] * (cmd["count"] - 1) // cmd["count"]

        # Tool usage
        for call in data.get("tool_calls", []):
            agg["tool_usage"][call.get("name", "unknown")] += 1

        # Timestamps
        all_timestamps.extend(data.get("timestamps", []))

    # Compute time span
    if all_timestamps:
        try:
            dates = [datetime.fromisoformat(ts.replace('Z', '+00:00')) for ts in all_timestamps if ts]
            if dates:
                agg["time_span_days"] = (max(dates) - min(dates)).days + 1
        except:
            pass

    agg["tool_usage"] = dict(agg["tool_usage"])
    return agg


def estimate_savings(agg: dict) -> dict:
    """Estimate potential savings from a diff/cache layer."""
    savings = {
        "bytes": {
            "current_transit": 0,
            "with_optimization": 0,
            "saved": 0,
            "saved_pct": 0
        },
        "tokens": {
            "wasted_estimate": 0,
            "saved_cost_estimate": 0
        },
        "latency": {
            "avoidable_round_trips_estimate": 0
        }
    }

    # Total bytes that transit currently
    current = (agg["total_bytes"]["read"] +
               agg["total_bytes"]["write"] +
               agg["total_bytes"]["bash_output"])

    # Bytes that could be avoided
    avoidable = (agg["inefficiencies"]["redundant_read_bytes"] +
                 agg["inefficiencies"]["diff_potential_bytes"] +
                 agg["inefficiencies"]["repeated_bash_bytes"])

    savings["bytes"]["current_transit"] = current
    savings["bytes"]["with_optimization"] = current - avoidable
    savings["bytes"]["saved"] = avoidable
    savings["bytes"]["saved_pct"] = round(100 * avoidable / current, 1) if current else 0

    # Estimate token waste (tool results go into context)
    wasted_tokens = avoidable // CHARS_PER_TOKEN
    savings["tokens"]["wasted_estimate"] = wasted_tokens
    savings["tokens"]["saved_cost_estimate"] = round(wasted_tokens / 1000 * COST_PER_1K_INPUT_TOKENS, 4)

    # Estimate avoidable round trips (redundant reads + repeated commands)
    # This is rough - assuming each could be served locally
    savings["latency"]["avoidable_round_trips_estimate"] = (
        agg["inefficiencies"]["redundant_read_bytes"] // 1000 +  # rough proxy
        len([1 for _ in range(10)])  # placeholder
    )

    return savings


def print_report(agg: dict, savings: dict, verbose: bool = False, sessions_data: list = None):
    """Print human-readable research report."""
    print("=" * 70)
    print("OPPORTUNITY SPACE ANALYSIS")
    print("Research Study: Potential for Local Diff/Cache Layer")
    print("=" * 70)

    print(f"\n📊 SCOPE")
    print(f"   Sessions analyzed: {agg['session_count']}")
    print(f"   Time span: {agg['time_span_days']} days")
    print(f"   Total tool calls: {agg['total_tool_calls']:,}")
    print(f"   Errors encountered: {agg['errors']}")

    print(f"\n📦 DATA TRANSIT (current)")
    print(f"   File reads:    {agg['total_bytes']['read']:,} bytes")
    print(f"   File writes:   {agg['total_bytes']['write']:,} bytes")
    print(f"   Bash output:   {agg['total_bytes']['bash_output']:,} bytes")
    total = sum(agg['total_bytes'].values())
    print(f"   Total:         {total:,} bytes ({total/1024/1024:.1f} MB)")

    print(f"\n🔴 IDENTIFIED INEFFICIENCIES")
    print(f"   Redundant file reads:  {agg['inefficiencies']['redundant_read_bytes']:,} bytes")
    print(f"   Diff potential:        {agg['inefficiencies']['diff_potential_bytes']:,} bytes")
    print(f"   Repeated bash output:  {agg['inefficiencies']['repeated_bash_bytes']:,} bytes")
    total_ineff = sum(agg['inefficiencies'].values())
    print(f"   Total avoidable:       {total_ineff:,} bytes")

    print(f"\n💰 TOKEN USAGE")
    print(f"   Input tokens:        {agg['total_tokens']['input']:,}")
    print(f"   Output tokens:       {agg['total_tokens']['output']:,}")
    print(f"   Cache read tokens:   {agg['total_tokens']['cache_read']:,}")
    print(f"   Cache write tokens:  {agg['total_tokens']['cache_write']:,}")

    print(f"\n🛠️  TOOL DISTRIBUTION")
    for tool, count in sorted(agg['tool_usage'].items(), key=lambda x: -x[1])[:10]:
        pct = 100 * count / agg['total_tool_calls'] if agg['total_tool_calls'] else 0
        print(f"   {tool}: {count:,} ({pct:.1f}%)")

    print(f"\n" + "=" * 70)
    print("POTENTIAL SAVINGS WITH LOCAL DIFF/CACHE LAYER")
    print("=" * 70)

    print(f"\n📉 TRANSIT REDUCTION")
    print(f"   Current:      {savings['bytes']['current_transit']:,} bytes")
    print(f"   Optimized:    {savings['bytes']['with_optimization']:,} bytes")
    print(f"   Saved:        {savings['bytes']['saved']:,} bytes ({savings['bytes']['saved_pct']}%)")

    print(f"\n💵 ESTIMATED TOKEN SAVINGS")
    print(f"   Wasted tokens (est):  {savings['tokens']['wasted_estimate']:,}")
    print(f"   Cost savings (est):   ${savings['tokens']['saved_cost_estimate']:.4f}")
    print(f"   (At ${COST_PER_1K_INPUT_TOKENS}/1K input tokens)")

    print(f"\n⏱️  LATENCY IMPACT")
    print(f"   A local cache/diff layer could serve redundant requests")
    print(f"   instantly instead of round-tripping to tools.")
    print(f"   Estimated avoidable operations: {savings['latency']['avoidable_round_trips_estimate']}")

    print(f"\n" + "=" * 70)
    print("EXTRAPOLATION: USER BENEFIT")
    print("=" * 70)

    # Project to larger scale
    if agg['session_count'] > 0 and agg['time_span_days'] > 0:
        daily_sessions = agg['session_count'] / agg['time_span_days']
        daily_waste = total_ineff / agg['time_span_days']
        monthly_waste = daily_waste * 30
        yearly_waste = daily_waste * 365

        print(f"\n   Based on {daily_sessions:.1f} sessions/day average:")
        print(f"   Monthly avoidable transit: {monthly_waste/1024/1024:.1f} MB")
        print(f"   Yearly avoidable transit:  {yearly_waste/1024/1024:.1f} MB")

        # Token projection
        monthly_tokens = savings['tokens']['wasted_estimate'] / agg['time_span_days'] * 30
        print(f"   Monthly token savings:     {monthly_tokens:,.0f} tokens")

    print(f"\n   User experience improvements:")
    print(f"   • Reduced latency on repeated file access")
    print(f"   • Extended context window efficiency")
    print(f"   • Lower API costs for equivalent work")
    print(f"   • Ability to work longer within rate limits")

    print(f"\n" + "=" * 70)
    print("RESEARCH NOTES")
    print("=" * 70)
    print("""
   This analysis identifies opportunities, not guarantees. A practical
   implementation would need to handle:

   • Cache invalidation (files change externally)
   • Diff computation overhead vs. savings
   • Memory/storage for local state
   • Protocol compatibility with tool layer

   The patterns identified here apply to any agentic AI tool system
   that performs file I/O through a tool-calling interface.

   This study is conducted in the spirit of responsible research -
   understanding system behavior to identify improvements, not exploits.
""")
    print("=" * 70)

    if verbose and sessions_data:
        print("\n\nPER-SESSION DETAILS:")
        print("-" * 70)
        for session in sessions_data:
            print(f"\n{session['path'].name}:")
            fa = session.get('file_analysis', {})
            print(f"  Reads: {fa.get('total_reads', 0)}, Redundant: {fa.get('redundant_bytes', 0):,}b")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Study opportunity space for diff/cache optimization")
    parser.add_argument("--project", type=Path, help="Analyze specific project directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Show per-session details")
    args = parser.parse_args()

    # Find sessions
    if args.project:
        sessions = [{"path": p, "project": args.project.name, "size": p.stat().st_size}
                    for p in args.project.glob("*.jsonl")]
    else:
        sessions = find_all_sessions()

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        sys.exit(1)

    # Analyze each session
    sessions_data = []
    for session in sessions:
        try:
            data = extract_session_data(session["path"])
            file_analysis = analyze_file_operations(data["tool_calls"])
            bash_analysis = analyze_bash_operations(data["tool_calls"])

            sessions_data.append({
                "path": session["path"],
                "project": session["project"],
                "data": data,
                "file_analysis": file_analysis,
                "bash_analysis": bash_analysis
            })
        except Exception as e:
            print(f"Warning: Failed to analyze {session['path']}: {e}", file=sys.stderr)

    # Aggregate
    agg = compute_aggregate_stats(sessions_data)
    savings = estimate_savings(agg)

    if args.json:
        output = {
            "aggregate": agg,
            "savings": savings,
            "sessions": [{
                "path": str(s["path"]),
                "project": s["project"],
                "file_analysis": s["file_analysis"],
                "bash_analysis": s["bash_analysis"]
            } for s in sessions_data]
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_report(agg, savings, args.verbose, sessions_data)


if __name__ == "__main__":
    main()
