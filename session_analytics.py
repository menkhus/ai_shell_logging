#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
session_analytics.py - Statistical analysis of Claude session metrics

Extracts ALL available metrics from Claude JSONL logs and performs
statistical analysis including:
- Descriptive statistics per column
- Correlation matrix
- Linear regression to identify predictors
- Error bars / confidence intervals

Usage:
    ./session_analytics.py                    # Full analysis to stdout
    ./session_analytics.py -o report.txt      # Save report
    ./session_analytics.py --csv metrics.csv  # Export enhanced CSV
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
import statistics
import math


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


def extract_full_metrics(jsonl_path: Path) -> dict:
    """Extract ALL available metrics from a session JSONL."""
    metrics = {
        "session_file": jsonl_path.name,
        "project": jsonl_path.parent.name,

        # Message counts
        "user_messages": 0,
        "assistant_messages": 0,
        "system_messages": 0,
        "total_messages": 0,

        # Tool metrics
        "tool_calls": 0,
        "tool_errors": 0,
        "tools_used": defaultdict(int),

        # Token metrics (THE BIG ONES WE WERE MISSING)
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "total_tokens": 0,

        # Timing
        "api_duration_ms": [],  # List for stats
        "first_timestamp": None,
        "last_timestamp": None,

        # Model info
        "models_used": defaultdict(int),

        # Stop reasons
        "stop_reasons": defaultdict(int),

        # Thinking metrics
        "thinking_blocks": 0,
        "thinking_tokens_budget": 0,

        # Retry metrics
        "retry_attempts": 0,
        "max_retries_seen": 0,

        # File operations
        "files_read": set(),
        "files_written": set(),
        "files_edited": set(),
        "bash_commands": 0,
        "bash_errors": 0,

        # Web usage
        "web_fetch_requests": 0,
        "web_search_requests": 0,

        # Context/compaction
        "compaction_events": 0,

        # Content size
        "bytes_to_llm": 0,
        "bytes_from_llm": 0,

        # First prompt
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

                # Timestamps
                if timestamp:
                    if metrics["first_timestamp"] is None:
                        metrics["first_timestamp"] = timestamp
                    metrics["last_timestamp"] = timestamp

                # Duration
                if "durationMs" in entry:
                    metrics["api_duration_ms"].append(entry["durationMs"])

                # Compaction
                if entry.get("isCompactSummary"):
                    metrics["compaction_events"] += 1

                # Message types
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

                    # Model
                    model = msg.get("model", "unknown")
                    metrics["models_used"][model] += 1

                    # Stop reason
                    stop_reason = msg.get("stop_reason", "unknown")
                    metrics["stop_reasons"][stop_reason] += 1

                    # Usage/tokens
                    usage = msg.get("usage", {})
                    metrics["input_tokens"] += usage.get("input_tokens", 0)
                    metrics["output_tokens"] += usage.get("output_tokens", 0)
                    metrics["cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
                    metrics["cache_creation_tokens"] += usage.get("cache_creation_input_tokens", 0)

                    # Server tool use
                    server_tools = usage.get("server_tool_use", {})
                    metrics["web_fetch_requests"] += server_tools.get("web_fetch_requests", 0)
                    metrics["web_search_requests"] += server_tools.get("web_search_requests", 0)

                elif msg_type == "summary":
                    metrics["system_messages"] += 1

                # Retry info
                if "retryAttempt" in entry:
                    metrics["retry_attempts"] += 1
                    metrics["max_retries_seen"] = max(
                        metrics["max_retries_seen"],
                        entry.get("maxRetries", 0)
                    )

                # Thinking metadata
                thinking = entry.get("thinkingMetadata", {})
                if thinking:
                    metrics["thinking_tokens_budget"] = max(
                        metrics["thinking_tokens_budget"],
                        thinking.get("maxThinkingTokens", 0)
                    )

                # Process content for tool calls
                msg = entry.get("message", {})
                content = msg.get("content", [])

                if isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            continue

                        item_type = item.get("type")

                        if item_type == "thinking":
                            metrics["thinking_blocks"] += 1

                        elif item_type == "tool_use":
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

                        elif item_type == "tool_result":
                            result = item.get("content", "")
                            if isinstance(result, str):
                                metrics["bytes_to_llm"] += len(result)
                            else:
                                metrics["bytes_to_llm"] += len(json.dumps(result))

                            if item.get("is_error"):
                                metrics["tool_errors"] += 1

                # Tool use results from toolUseResult
                tool_result = entry.get("toolUseResult", {})
                if tool_result:
                    if tool_result.get("success") == False:
                        metrics["bash_errors"] += 1

    except Exception as e:
        metrics["error"] = str(e)

    # Compute derived metrics
    metrics["total_tokens"] = (
        metrics["input_tokens"] +
        metrics["output_tokens"]
    )

    return metrics


def metrics_to_row(metrics: dict) -> dict:
    """Convert metrics dict to flat CSV row with all fields."""

    # Duration calculation
    duration_minutes = None
    if metrics["first_timestamp"] and metrics["last_timestamp"]:
        try:
            first = datetime.fromisoformat(metrics["first_timestamp"].replace("Z", "+00:00"))
            last = datetime.fromisoformat(metrics["last_timestamp"].replace("Z", "+00:00"))
            duration_minutes = (last - first).total_seconds() / 60
        except:
            pass

    # API duration stats
    api_durations = metrics["api_duration_ms"]
    api_dur_mean = statistics.mean(api_durations) if api_durations else 0
    api_dur_std = statistics.stdev(api_durations) if len(api_durations) > 1 else 0
    api_dur_max = max(api_durations) if api_durations else 0

    # Tools
    tools_used = metrics["tools_used"]
    top_tools = sorted(tools_used.items(), key=lambda x: -x[1])[:5]
    top_tools_str = ", ".join(f"{t}:{c}" for t, c in top_tools)

    # Model
    models = metrics["models_used"]
    primary_model = max(models.items(), key=lambda x: x[1])[0] if models else "unknown"

    # Cache efficiency
    total_input = metrics["input_tokens"]
    cache_read = metrics["cache_read_tokens"]
    cache_hit_rate = (cache_read / total_input * 100) if total_input > 0 else 0

    # Error rate
    tool_calls = metrics["tool_calls"]
    tool_errors = metrics["tool_errors"]
    error_rate = (tool_errors / tool_calls * 100) if tool_calls > 0 else 0

    return {
        # Identity
        "session_file": metrics["session_file"],
        "project": metrics["project"],
        "date": metrics["first_timestamp"][:10] if metrics["first_timestamp"] else "",

        # Time
        "duration_min": round(duration_minutes, 1) if duration_minutes else 0,
        "api_dur_mean_ms": round(api_dur_mean, 0),
        "api_dur_std_ms": round(api_dur_std, 0),
        "api_dur_max_ms": round(api_dur_max, 0),

        # Messages
        "user_msgs": metrics["user_messages"],
        "assistant_msgs": metrics["assistant_messages"],
        "total_msgs": metrics["total_messages"],

        # Tokens (THE KEY METRICS)
        "input_tokens": metrics["input_tokens"],
        "output_tokens": metrics["output_tokens"],
        "total_tokens": metrics["total_tokens"],
        "cache_read_tokens": metrics["cache_read_tokens"],
        "cache_creation_tokens": metrics["cache_creation_tokens"],
        "cache_hit_rate_pct": round(cache_hit_rate, 1),

        # Tools
        "tool_calls": tool_calls,
        "tool_errors": tool_errors,
        "error_rate_pct": round(error_rate, 1),

        # File ops
        "files_read": len(metrics["files_read"]),
        "files_written": len(metrics["files_written"]),
        "files_edited": len(metrics["files_edited"]),
        "bash_cmds": metrics["bash_commands"],
        "bash_errors": metrics["bash_errors"],

        # Web
        "web_fetches": metrics["web_fetch_requests"],
        "web_searches": metrics["web_search_requests"],

        # Thinking
        "thinking_blocks": metrics["thinking_blocks"],

        # Retries
        "retry_attempts": metrics["retry_attempts"],

        # Context
        "compaction_events": metrics["compaction_events"],
        "bytes_to_llm": metrics["bytes_to_llm"],
        "bytes_from_llm": metrics["bytes_from_llm"],

        # Model
        "model": primary_model,

        # Meta
        "top_tools": top_tools_str,
        "first_prompt": metrics["first_prompt"].replace("\n", " ")[:80],
    }


# ============================================================================
# STATISTICAL ANALYSIS
# ============================================================================

def compute_column_stats(rows: list, column: str) -> dict:
    """Compute descriptive statistics for a numeric column."""
    values = []
    for row in rows:
        val = row.get(column)
        if val is not None and val != "" and not isinstance(val, str):
            try:
                values.append(float(val))
            except (ValueError, TypeError):
                pass

    if not values:
        return {"n": 0, "error": "no numeric data"}

    n = len(values)
    mean = statistics.mean(values)

    stats = {
        "n": n,
        "mean": mean,
        "min": min(values),
        "max": max(values),
        "sum": sum(values),
    }

    if n > 1:
        stats["std"] = statistics.stdev(values)
        stats["stderr"] = stats["std"] / math.sqrt(n)  # For error bars
        stats["ci_95_low"] = mean - 1.96 * stats["stderr"]
        stats["ci_95_high"] = mean + 1.96 * stats["stderr"]
        stats["median"] = statistics.median(values)

        # Quartiles
        sorted_vals = sorted(values)
        q1_idx = int(n * 0.25)
        q3_idx = int(n * 0.75)
        stats["q1"] = sorted_vals[q1_idx]
        stats["q3"] = sorted_vals[q3_idx]
        stats["iqr"] = stats["q3"] - stats["q1"]
    else:
        stats["std"] = 0
        stats["stderr"] = 0
        stats["median"] = mean

    return stats


def compute_correlation(rows: list, col_x: str, col_y: str) -> dict:
    """Compute Pearson correlation between two columns."""
    pairs = []
    for row in rows:
        x = row.get(col_x)
        y = row.get(col_y)
        if x is not None and y is not None and x != "" and y != "":
            try:
                pairs.append((float(x), float(y)))
            except (ValueError, TypeError):
                pass

    if len(pairs) < 3:
        return {"r": None, "n": len(pairs), "error": "insufficient data"}

    n = len(pairs)
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]

    mean_x = statistics.mean(x_vals)
    mean_y = statistics.mean(y_vals)

    # Pearson correlation
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_vals))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_vals))

    if denom_x == 0 or denom_y == 0:
        return {"r": 0, "n": n, "error": "zero variance"}

    r = numerator / (denom_x * denom_y)

    # R-squared
    r_squared = r ** 2

    return {
        "r": round(r, 3),
        "r_squared": round(r_squared, 3),
        "n": n,
        "interpretation": interpret_correlation(r)
    }


def interpret_correlation(r: float) -> str:
    """Interpret correlation coefficient."""
    if r is None:
        return "undefined"
    abs_r = abs(r)
    if abs_r < 0.1:
        return "negligible"
    elif abs_r < 0.3:
        return "weak"
    elif abs_r < 0.5:
        return "moderate"
    elif abs_r < 0.7:
        return "strong"
    else:
        return "very strong"


def linear_regression(rows: list, x_col: str, y_col: str) -> dict:
    """Simple linear regression: y = mx + b."""
    pairs = []
    for row in rows:
        x = row.get(x_col)
        y = row.get(y_col)
        if x is not None and y is not None and x != "" and y != "":
            try:
                pairs.append((float(x), float(y)))
            except (ValueError, TypeError):
                pass

    if len(pairs) < 3:
        return {"error": "insufficient data", "n": len(pairs)}

    n = len(pairs)
    x_vals = [p[0] for p in pairs]
    y_vals = [p[1] for p in pairs]

    mean_x = statistics.mean(x_vals)
    mean_y = statistics.mean(y_vals)

    # Slope and intercept
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    denominator = sum((x - mean_x) ** 2 for x in x_vals)

    if denominator == 0:
        return {"error": "zero variance in x", "n": n}

    slope = numerator / denominator
    intercept = mean_y - slope * mean_x

    # Predictions and residuals
    predictions = [slope * x + intercept for x in x_vals]
    residuals = [y - pred for y, pred in zip(y_vals, predictions)]

    # R-squared
    ss_res = sum(r ** 2 for r in residuals)
    ss_tot = sum((y - mean_y) ** 2 for y in y_vals)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # Standard error of slope
    if n > 2:
        mse = ss_res / (n - 2)
        se_slope = math.sqrt(mse / denominator) if mse > 0 else 0
    else:
        se_slope = 0

    return {
        "slope": round(slope, 6),
        "intercept": round(intercept, 3),
        "r_squared": round(r_squared, 3),
        "se_slope": round(se_slope, 6),
        "n": n,
        "interpretation": f"For each unit increase in {x_col}, {y_col} changes by {slope:.4f}"
    }


def generate_analysis_report(rows: list) -> str:
    """Generate full statistical analysis report."""

    report = []
    report.append("=" * 70)
    report.append("CLAUDE SESSION METRICS - STATISTICAL ANALYSIS")
    report.append("=" * 70)
    report.append(f"\nTotal sessions analyzed: {len(rows)}")

    # Numeric columns for analysis
    numeric_cols = [
        "duration_min", "api_dur_mean_ms", "user_msgs", "assistant_msgs",
        "total_msgs", "input_tokens", "output_tokens", "total_tokens",
        "cache_read_tokens", "cache_hit_rate_pct", "tool_calls",
        "tool_errors", "error_rate_pct", "files_read", "files_edited",
        "bash_cmds", "thinking_blocks", "retry_attempts", "compaction_events",
        "bytes_to_llm", "bytes_from_llm"
    ]

    # 1. DESCRIPTIVE STATISTICS
    report.append("\n" + "=" * 70)
    report.append("1. DESCRIPTIVE STATISTICS (with 95% CI for error bars)")
    report.append("=" * 70)

    for col in numeric_cols:
        stats = compute_column_stats(rows, col)
        if stats.get("n", 0) > 0:
            report.append(f"\n{col}:")
            report.append(f"  N={stats['n']}, Mean={stats['mean']:.2f}, Std={stats.get('std', 0):.2f}")
            report.append(f"  Min={stats['min']:.2f}, Max={stats['max']:.2f}, Median={stats.get('median', 0):.2f}")
            if 'ci_95_low' in stats:
                report.append(f"  95% CI: [{stats['ci_95_low']:.2f}, {stats['ci_95_high']:.2f}]")
                report.append(f"  StdErr={stats['stderr']:.3f} (use for error bars)")

    # 2. CORRELATION MATRIX (key pairs)
    report.append("\n" + "=" * 70)
    report.append("2. CORRELATION ANALYSIS")
    report.append("=" * 70)
    report.append("\nKey correlations (|r| > 0.3 shown):\n")

    interesting_pairs = [
        ("user_msgs", "total_tokens"),
        ("user_msgs", "tool_calls"),
        ("user_msgs", "duration_min"),
        ("tool_calls", "tool_errors"),
        ("tool_calls", "total_tokens"),
        ("input_tokens", "output_tokens"),
        ("duration_min", "total_tokens"),
        ("files_edited", "tool_errors"),
        ("bash_cmds", "bash_errors"),
        ("cache_hit_rate_pct", "input_tokens"),
        ("thinking_blocks", "output_tokens"),
        ("compaction_events", "total_msgs"),
    ]

    correlations = []
    for x, y in interesting_pairs:
        corr = compute_correlation(rows, x, y)
        if corr.get("r") is not None and abs(corr["r"]) > 0.3:
            correlations.append((x, y, corr))

    correlations.sort(key=lambda x: abs(x[2]["r"]), reverse=True)

    for x, y, corr in correlations:
        report.append(f"  {x} vs {y}: r={corr['r']}, R²={corr['r_squared']} ({corr['interpretation']})")

    # 3. LINEAR REGRESSION - What predicts errors?
    report.append("\n" + "=" * 70)
    report.append("3. LINEAR REGRESSION - PREDICTORS OF KEY OUTCOMES")
    report.append("=" * 70)

    # What predicts tool errors?
    report.append("\n--- What predicts TOOL ERRORS? ---")
    predictors = ["tool_calls", "bash_cmds", "files_edited", "duration_min", "user_msgs"]
    for pred in predictors:
        reg = linear_regression(rows, pred, "tool_errors")
        if "slope" in reg:
            report.append(f"  {pred}: slope={reg['slope']:.4f}, R²={reg['r_squared']:.3f}")

    # What predicts token usage?
    report.append("\n--- What predicts TOTAL TOKENS? ---")
    predictors = ["user_msgs", "tool_calls", "duration_min", "files_read"]
    for pred in predictors:
        reg = linear_regression(rows, pred, "total_tokens")
        if "slope" in reg:
            report.append(f"  {pred}: slope={reg['slope']:.1f}, R²={reg['r_squared']:.3f}")

    # What predicts duration?
    report.append("\n--- What predicts SESSION DURATION? ---")
    predictors = ["user_msgs", "tool_calls", "total_tokens", "files_edited"]
    for pred in predictors:
        reg = linear_regression(rows, pred, "duration_min")
        if "slope" in reg:
            report.append(f"  {pred}: slope={reg['slope']:.4f}, R²={reg['r_squared']:.3f}")

    # 4. CAUSALITY DISCUSSION
    report.append("\n" + "=" * 70)
    report.append("4. ON CAUSALITY")
    report.append("=" * 70)
    report.append("""
IMPORTANT: These are CORRELATIONS, not causal relationships.

We can identify ASSOCIATIONS (what tends to occur together):
  - More tool calls → more errors (but errors may not be "caused by" tool count)
  - Longer sessions → more tokens (but which causes which?)

We CANNOT determine causality because:
  1. No experimental control - sessions vary in many ways simultaneously
  2. Confounding variables - task complexity affects both duration AND errors
  3. Reverse causation - do errors cause retries, or do retries reveal errors?
  4. Selection bias - only completed sessions are logged

To establish causality, you would need:
  - A/B experiments (randomize some factor)
  - Instrumental variables
  - Natural experiments
  - Time-series analysis with Granger causality

What we CAN say: "Sessions with X tend to have more Y"
What we CANNOT say: "X causes Y"
""")

    # 5. ERROR BAR DATA
    report.append("\n" + "=" * 70)
    report.append("5. ERROR BAR DATA (for plotting)")
    report.append("=" * 70)
    report.append("\nFormat: column, mean, stderr (for ±1 SE error bars)")
    report.append("        or use ci_95_low/high for 95% confidence intervals\n")

    for col in ["total_tokens", "tool_errors", "duration_min", "error_rate_pct"]:
        stats = compute_column_stats(rows, col)
        if stats.get("n", 0) > 1:
            report.append(f"{col}:")
            report.append(f"  mean={stats['mean']:.2f} ± {stats.get('stderr', 0):.2f} (SE)")
            if 'ci_95_low' in stats:
                report.append(f"  95% CI: [{stats['ci_95_low']:.2f}, {stats['ci_95_high']:.2f}]")

    return "\n".join(report)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Statistical analysis of Claude sessions")
    parser.add_argument("-o", "--output", type=Path, help="Save report to file")
    parser.add_argument("--csv", type=Path, help="Export enhanced CSV with all metrics")
    parser.add_argument("--dir", type=Path, help="Claude projects dir")
    parser.add_argument("--stats-csv", type=Path, help="Export column statistics as CSV")
    args = parser.parse_args()

    sessions = find_claude_sessions(args.dir)

    if not sessions:
        print("No Claude sessions found.", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(sessions)} sessions...", file=sys.stderr)

    rows = []
    for session in sessions:
        metrics = extract_full_metrics(session["path"])
        row = metrics_to_row(metrics)
        rows.append(row)

    rows.sort(key=lambda x: x["date"], reverse=True)

    # Export enhanced CSV if requested
    if args.csv:
        fieldnames = list(rows[0].keys())
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n>>> ENHANCED CSV: {args.csv.absolute()}", file=sys.stderr)

    # Generate and output report
    report = generate_analysis_report(rows)

    if args.output:
        args.output.write_text(report)
        print(f">>> REPORT: {args.output.absolute()}", file=sys.stderr)
    else:
        print(report)

    # Export stats CSV if requested
    if args.stats_csv:
        numeric_cols = [
            "duration_min", "api_dur_mean_ms", "user_msgs", "assistant_msgs",
            "total_msgs", "input_tokens", "output_tokens", "total_tokens",
            "cache_read_tokens", "cache_hit_rate_pct", "tool_calls",
            "tool_errors", "error_rate_pct", "files_read", "files_edited",
            "bash_cmds", "thinking_blocks", "retry_attempts"
        ]

        stats_rows = []
        for col in numeric_cols:
            stats = compute_column_stats(rows, col)
            stats["column"] = col
            stats_rows.append(stats)

        with open(args.stats_csv, "w", newline="") as f:
            fieldnames = ["column", "n", "mean", "std", "stderr", "min", "max",
                          "median", "q1", "q3", "ci_95_low", "ci_95_high"]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(stats_rows)
        print(f">>> STATS CSV: {args.stats_csv.absolute()}", file=sys.stderr)


if __name__ == "__main__":
    main()
