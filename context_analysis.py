#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
context_analysis.py - Analyze Claude context management patterns

Engineers love tweaking context. This tool shows:
- Cache efficiency per project/session
- Compaction events (context overflow)
- Token usage patterns
- Cost implications
- Recommendations for context optimization

Usage:
    ./context_analysis.py                    # Full report
    ./context_analysis.py --project NAME     # Single project
    ./context_analysis.py --csv context.csv  # Export data
"""

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import statistics


@dataclass
class SessionContext:
    """Context metrics for a single session."""
    session_id: str
    project: str
    date: str

    # Token counts
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_create: int = 0

    # Ephemeral cache
    ephemeral_5m: int = 0
    ephemeral_1h: int = 0

    # Events
    compactions: int = 0
    compaction_triggers: list = field(default_factory=list)
    api_calls: int = 0

    # Timing
    duration_minutes: float = 0

    @property
    def total_context(self) -> int:
        return self.cache_read + self.input_tokens

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_read + self.input_tokens
        return (self.cache_read / total * 100) if total > 0 else 0

    @property
    def tokens_per_minute(self) -> float:
        if self.duration_minutes > 0:
            return self.total_context / self.duration_minutes
        return 0

    @property
    def estimated_cost(self) -> float:
        """Estimate cost in USD (Opus pricing)."""
        cache_read_cost = self.cache_read / 1e6 * 0.30
        cache_write_cost = self.cache_create / 1e6 * 3.75
        input_cost = self.input_tokens / 1e6 * 3.00
        output_cost = self.output_tokens / 1e6 * 15.00
        return cache_read_cost + cache_write_cost + input_cost + output_cost


def extract_session_context(jsonl_path: Path) -> SessionContext:
    """Extract context metrics from a session JSONL."""

    ctx = SessionContext(
        session_id=jsonl_path.stem[:8],
        project=jsonl_path.parent.name[-40:],
        date="",
    )

    first_ts = None
    last_ts = None

    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except:
                    continue

                # Timestamps
                ts = obj.get("timestamp")
                if ts:
                    if first_ts is None:
                        first_ts = ts
                        ctx.date = ts[:10]
                    last_ts = ts

                # Usage
                usage = obj.get("message", {}).get("usage", {})
                if usage:
                    ctx.api_calls += 1
                    ctx.input_tokens += usage.get("input_tokens", 0)
                    ctx.output_tokens += usage.get("output_tokens", 0)
                    ctx.cache_read += usage.get("cache_read_input_tokens", 0)
                    ctx.cache_create += usage.get("cache_creation_input_tokens", 0)

                    # Ephemeral
                    cc = usage.get("cache_creation", {})
                    ctx.ephemeral_5m += cc.get("ephemeral_5m_input_tokens", 0)
                    ctx.ephemeral_1h += cc.get("ephemeral_1h_input_tokens", 0)

                # Compaction
                if obj.get("isCompactSummary"):
                    ctx.compactions += 1
                    meta = obj.get("compactMetadata", {})
                    if meta.get("trigger"):
                        ctx.compaction_triggers.append(meta["trigger"])

    except Exception as e:
        pass

    # Duration
    if first_ts and last_ts:
        try:
            first = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            last = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            ctx.duration_minutes = (last - first).total_seconds() / 60
        except:
            pass

    return ctx


def analyze_all_sessions() -> list[SessionContext]:
    """Analyze all Claude sessions."""
    projects_dir = Path.home() / ".claude" / "projects"
    sessions = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        for jsonl in project_dir.glob("*.jsonl"):
            ctx = extract_session_context(jsonl)
            if ctx.api_calls > 0:
                sessions.append(ctx)

    return sessions


def identify_context_issues(sessions: list[SessionContext]) -> list[dict]:
    """Identify sessions with context management issues."""
    issues = []

    for s in sessions:
        session_issues = []

        # Low cache hit rate
        if s.total_context > 10000 and s.cache_hit_rate < 50:
            session_issues.append({
                "type": "low_cache_hit",
                "severity": "warning",
                "message": f"Cache hit rate only {s.cache_hit_rate:.0f}%",
            })

        # Compaction (context overflow)
        if s.compactions > 0:
            session_issues.append({
                "type": "compaction",
                "severity": "info",
                "message": f"{s.compactions} compaction(s) - context overflowed",
                "triggers": s.compaction_triggers,
            })

        # High token burn rate
        if s.tokens_per_minute > 50000:
            session_issues.append({
                "type": "high_burn",
                "severity": "warning",
                "message": f"High token rate: {s.tokens_per_minute:.0f}/min",
            })

        # Expensive session
        if s.estimated_cost > 1.0:
            session_issues.append({
                "type": "expensive",
                "severity": "info",
                "message": f"Session cost: ${s.estimated_cost:.2f}",
            })

        # No caching (small session, might be inefficient)
        if s.cache_read == 0 and s.input_tokens > 5000:
            session_issues.append({
                "type": "no_cache",
                "severity": "warning",
                "message": "No cache reads - context not being reused",
            })

        if session_issues:
            issues.append({
                "session": s.session_id,
                "project": s.project,
                "date": s.date,
                "issues": session_issues,
            })

    return issues


def generate_report(sessions: list[SessionContext]) -> str:
    """Generate context management report."""

    report = []
    report.append("=" * 75)
    report.append("CONTEXT MANAGEMENT ANALYSIS")
    report.append("=" * 75)

    # Aggregate stats
    total_cache_read = sum(s.cache_read for s in sessions)
    total_cache_create = sum(s.cache_create for s in sessions)
    total_input = sum(s.input_tokens for s in sessions)
    total_output = sum(s.output_tokens for s in sessions)
    total_compactions = sum(s.compactions for s in sessions)
    total_cost = sum(s.estimated_cost for s in sessions)

    report.append(f"\nSessions analyzed: {len(sessions)}")
    report.append(f"Total estimated cost: ${total_cost:.2f}")

    # Cache efficiency
    report.append("\n" + "-" * 75)
    report.append("CACHE EFFICIENCY")
    report.append("-" * 75)

    if total_cache_read + total_input > 0:
        overall_hit_rate = total_cache_read / (total_cache_read + total_input) * 100
        report.append(f"\nOverall cache hit rate: {overall_hit_rate:.1f}%")

    report.append(f"\nToken breakdown:")
    report.append(f"  Cache read:     {total_cache_read:>15,} tokens ({total_cache_read/1e6:.1f}M)")
    report.append(f"  Cache create:   {total_cache_create:>15,} tokens ({total_cache_create/1e6:.1f}M)")
    report.append(f"  Fresh input:    {total_input:>15,} tokens")
    report.append(f"  Output:         {total_output:>15,} tokens")

    # Cost breakdown
    report.append("\n" + "-" * 75)
    report.append("COST BREAKDOWN (Opus pricing)")
    report.append("-" * 75)

    cache_read_cost = total_cache_read / 1e6 * 0.30
    cache_write_cost = total_cache_create / 1e6 * 3.75
    input_cost = total_input / 1e6 * 3.00
    output_cost = total_output / 1e6 * 15.00

    report.append(f"\n  Cache read  ($0.30/1M):  ${cache_read_cost:>8.2f}")
    report.append(f"  Cache write ($3.75/1M):  ${cache_write_cost:>8.2f}")
    report.append(f"  Fresh input ($3.00/1M):  ${input_cost:>8.2f}")
    report.append(f"  Output      ($15.0/1M):  ${output_cost:>8.2f}")
    report.append(f"  ---------------------------")
    report.append(f"  TOTAL:                   ${total_cost:>8.2f}")

    # Savings calculation
    no_cache_cost = (total_cache_read + total_input) / 1e6 * 3.00 + output_cost
    savings = no_cache_cost - total_cost
    savings_pct = (savings / no_cache_cost * 100) if no_cache_cost > 0 else 0

    report.append(f"\n  Without caching: ${no_cache_cost:.2f}")
    report.append(f"  Cache savings:   ${savings:.2f} ({savings_pct:.0f}%)")

    # Compaction events
    report.append("\n" + "-" * 75)
    report.append("COMPACTION EVENTS (Context Overflow)")
    report.append("-" * 75)

    report.append(f"\nTotal compaction events: {total_compactions}")

    compaction_sessions = [s for s in sessions if s.compactions > 0]
    if compaction_sessions:
        report.append(f"Sessions with compaction: {len(compaction_sessions)}")
        report.append("\nCompaction details:")
        for s in sorted(compaction_sessions, key=lambda x: -x.compactions)[:5]:
            triggers = ", ".join(s.compaction_triggers[:2]) if s.compaction_triggers else "unknown"
            report.append(f"  {s.session_id} ({s.project[:25]}): {s.compactions}x, triggers: {triggers}")

    # Sessions by context usage
    report.append("\n" + "-" * 75)
    report.append("TOP SESSIONS BY CONTEXT USAGE")
    report.append("-" * 75)

    by_context = sorted(sessions, key=lambda x: -x.total_context)[:10]
    report.append(f"\n{'Session':<10} {'Project':<28} {'Context':>12} {'Cache%':>8} {'Cost':>8}")
    report.append("-" * 75)

    for s in by_context:
        ctx_str = f"{s.total_context/1e6:.1f}M" if s.total_context > 1e6 else f"{s.total_context/1e3:.0f}K"
        report.append(f"{s.session_id:<10} {s.project[:28]:<28} {ctx_str:>12} {s.cache_hit_rate:>7.0f}% ${s.estimated_cost:>6.2f}")

    # Issues
    issues = identify_context_issues(sessions)

    report.append("\n" + "-" * 75)
    report.append("CONTEXT ISSUES DETECTED")
    report.append("-" * 75)

    if issues:
        issue_counts = defaultdict(int)
        for i in issues:
            for issue in i["issues"]:
                issue_counts[issue["type"]] += 1

        report.append("\nIssue summary:")
        for issue_type, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            report.append(f"  {count:3d}x {issue_type}")

        report.append("\nRecent issues:")
        for i in sorted(issues, key=lambda x: x["date"], reverse=True)[:5]:
            issue_msgs = [iss["message"] for iss in i["issues"]]
            report.append(f"  {i['date']} {i['session']}: {'; '.join(issue_msgs)}")
    else:
        report.append("\n✅ No significant context issues detected!")

    # Recommendations
    report.append("\n" + "=" * 75)
    report.append("CONTEXT OPTIMIZATION RECOMMENDATIONS")
    report.append("=" * 75)

    recommendations = []

    if total_compactions > len(sessions) * 0.1:
        recommendations.append(
            "🔄 COMPACTION: Many sessions hit context limits.\n"
            "   Try: Break long tasks into smaller sessions. Use /clear between unrelated tasks."
        )

    if overall_hit_rate < 90:
        recommendations.append(
            "💾 CACHE: Cache hit rate below 90%.\n"
            "   Try: Reuse sessions for related work. Avoid starting fresh sessions frequently."
        )

    low_cache_sessions = [s for s in sessions if s.cache_hit_rate < 50 and s.total_context > 10000]
    if len(low_cache_sessions) > 5:
        recommendations.append(
            f"⚠️  {len(low_cache_sessions)} sessions have <50% cache hit rate.\n"
            "   Try: Continue existing sessions rather than starting new ones."
        )

    expensive = [s for s in sessions if s.estimated_cost > 1.0]
    if expensive:
        total_expensive = sum(s.estimated_cost for s in expensive)
        recommendations.append(
            f"💰 COST: {len(expensive)} sessions cost >$1 (total: ${total_expensive:.2f}).\n"
            "   These are your context-heavy sessions. Review if the work justified the cost."
        )

    if not recommendations:
        recommendations.append("✅ Context management looks good! Cache is being used effectively.")

    for rec in recommendations:
        report.append(f"\n{rec}")

    return "\n".join(report)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Claude context management")
    parser.add_argument("--project", type=str, help="Filter to specific project")
    parser.add_argument("--csv", type=Path, help="Export session context data as CSV")
    parser.add_argument("-o", "--output", type=Path, help="Save report to file")
    args = parser.parse_args()

    print("Analyzing context management...", end="", flush=True)
    sessions = analyze_all_sessions()
    print(f" found {len(sessions)} sessions")

    if args.project:
        sessions = [s for s in sessions if args.project.lower() in s.project.lower()]
        print(f"Filtered to {len(sessions)} sessions in project matching '{args.project}'")

    if not sessions:
        print("No sessions found.")
        return 1

    # Generate report
    report = generate_report(sessions)

    if args.output:
        args.output.write_text(report)
        print(f"\n>>> REPORT: {args.output.absolute()}")
    else:
        print(report)

    # Export CSV
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            fieldnames = [
                "session_id", "project", "date", "duration_min",
                "input_tokens", "output_tokens", "cache_read", "cache_create",
                "cache_hit_rate", "tokens_per_min", "compactions", "estimated_cost"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for s in sessions:
                writer.writerow({
                    "session_id": s.session_id,
                    "project": s.project,
                    "date": s.date,
                    "duration_min": round(s.duration_minutes, 1),
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "cache_read": s.cache_read,
                    "cache_create": s.cache_create,
                    "cache_hit_rate": round(s.cache_hit_rate, 1),
                    "tokens_per_min": round(s.tokens_per_minute, 0),
                    "compactions": s.compactions,
                    "estimated_cost": round(s.estimated_cost, 3),
                })

        print(f"\n>>> CONTEXT CSV: {args.csv.absolute()}")


if __name__ == "__main__":
    main()
