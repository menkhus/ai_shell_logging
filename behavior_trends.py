#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
behavior_trends.py - Track user behavior improvement over time

Shows week-over-week trends in:
- Prompt quality
- Session focus
- Efficiency
- Error avoidance
- Overall score

Usage:
    ./behavior_trends.py                    # Show trends report
    ./behavior_trends.py --csv trends.csv   # Export weekly data
"""

import csv
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def parse_week(date_str: str) -> str:
    """Convert date string to ISO week (YYYY-WXX)."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
    except:
        return "unknown"


def get_week_start(date_str: str) -> str:
    """Get the Monday of the week for a date."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday = dt - timedelta(days=dt.weekday())
        return monday.strftime("%Y-%m-%d")
    except:
        return date_str


def trend_arrow(current: float, previous: float) -> str:
    """Get trend indicator."""
    if previous == 0:
        return "  "
    diff = current - previous
    pct = (diff / previous) * 100 if previous != 0 else 0

    if abs(pct) < 5:
        return "→ "
    elif pct > 20:
        return "⬆️"
    elif pct > 0:
        return "↗ "
    elif pct < -20:
        return "⬇️"
    else:
        return "↘ "


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Track user behavior trends over time")
    parser.add_argument("--csv", type=Path, help="Export weekly trends as CSV")
    parser.add_argument("--scores", type=Path, default=Path("user_behavior_scores.csv"),
                        help="Input scores CSV")
    args = parser.parse_args()

    if not args.scores.exists():
        print(f"Error: {args.scores} not found. Run user_behavior_analysis.py first.")
        return 1

    # Load scores
    sessions = []
    with open(args.scores) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date"):
                sessions.append(row)

    if not sessions:
        print("No sessions with dates found.")
        return 1

    # Group by week
    weekly_data = defaultdict(list)
    for s in sessions:
        week = parse_week(s["date"])
        if week != "unknown":
            weekly_data[week].append({
                "prompt_quality": float(s.get("prompt_quality", 0) or 0),
                "session_focus": float(s.get("session_focus", 0) or 0),
                "efficiency": float(s.get("efficiency", 0) or 0),
                "error_avoidance": float(s.get("error_avoidance", 0) or 0),
                "overall_score": float(s.get("overall_score", 0) or 0),
                "files_edited": int(s.get("files_edited", 0) or 0),
                "user_msgs": int(s.get("user_msgs", 0) or 0),
            })

    # Sort weeks
    weeks = sorted(weekly_data.keys())

    if len(weeks) < 1:
        print("Not enough data for trends.")
        return 1

    # Compute weekly averages
    weekly_stats = []
    for week in weeks:
        data = weekly_data[week]
        n = len(data)

        stats = {
            "week": week,
            "sessions": n,
            "prompt_quality": statistics.mean(d["prompt_quality"] for d in data),
            "session_focus": statistics.mean(d["session_focus"] for d in data),
            "efficiency": statistics.mean(d["efficiency"] for d in data),
            "error_avoidance": statistics.mean(d["error_avoidance"] for d in data),
            "overall_score": statistics.mean(d["overall_score"] for d in data),
            "total_edits": sum(d["files_edited"] for d in data),
            "total_msgs": sum(d["user_msgs"] for d in data),
            "productive_sessions": sum(1 for d in data if d["files_edited"] > 0),
        }

        # Standard error for confidence
        if n > 1:
            stats["overall_stderr"] = statistics.stdev(d["overall_score"] for d in data) / (n ** 0.5)
        else:
            stats["overall_stderr"] = 0

        weekly_stats.append(stats)

    # Report
    print("=" * 78)
    print("USER BEHAVIOR TRENDS - WEEK OVER WEEK")
    print("=" * 78)
    print(f"\nData range: {weeks[0]} to {weeks[-1]} ({len(weeks)} weeks)")
    print(f"Total sessions: {len(sessions)}")

    # Weekly breakdown
    print("\n" + "-" * 78)
    print(f"{'Week':<10} {'N':>4} {'Overall':>10} {'Prompt':>10} {'Focus':>10} {'Effic':>10} {'Trend':>6}")
    print("-" * 78)

    prev_overall = None
    for stats in weekly_stats:
        trend = trend_arrow(stats["overall_score"], prev_overall) if prev_overall else "  "

        print(f"{stats['week']:<10} {stats['sessions']:>4} "
              f"{stats['overall_score']:>9.1f} "
              f"{stats['prompt_quality']:>9.1f} "
              f"{stats['session_focus']:>9.1f} "
              f"{stats['efficiency']:>9.1f} "
              f"  {trend}")

        prev_overall = stats["overall_score"]

    # Trend analysis
    print("\n" + "=" * 78)
    print("TREND ANALYSIS")
    print("=" * 78)

    if len(weekly_stats) >= 2:
        first_half = weekly_stats[:len(weekly_stats)//2]
        second_half = weekly_stats[len(weekly_stats)//2:]

        first_avg = statistics.mean(s["overall_score"] for s in first_half)
        second_avg = statistics.mean(s["overall_score"] for s in second_half)

        change = second_avg - first_avg
        pct_change = (change / first_avg * 100) if first_avg > 0 else 0

        print(f"\nFirst half average:  {first_avg:.1f}/100")
        print(f"Second half average: {second_avg:.1f}/100")
        print(f"Change: {change:+.1f} ({pct_change:+.1f}%)")

        if pct_change > 10:
            print("\n✅ IMPROVING: Your Claude usage is getting better!")
        elif pct_change < -10:
            print("\n⚠️  DECLINING: Consider reviewing best practices.")
        else:
            print("\n→  STABLE: Consistent behavior over time.")

    # Best and worst weeks
    print("\n" + "-" * 78)
    print("NOTABLE WEEKS")
    print("-" * 78)

    best = max(weekly_stats, key=lambda x: x["overall_score"])
    worst = min(weekly_stats, key=lambda x: x["overall_score"])
    most_productive = max(weekly_stats, key=lambda x: x["total_edits"])

    print(f"\nBest week:          {best['week']} (score: {best['overall_score']:.1f}, {best['sessions']} sessions)")
    print(f"Worst week:         {worst['week']} (score: {worst['overall_score']:.1f}, {worst['sessions']} sessions)")
    print(f"Most productive:    {most_productive['week']} ({most_productive['total_edits']} file edits)")

    # Metric-specific trends
    print("\n" + "-" * 78)
    print("METRIC BREAKDOWN (first week → last week)")
    print("-" * 78)

    first = weekly_stats[0]
    last = weekly_stats[-1]

    metrics = ["prompt_quality", "session_focus", "efficiency", "error_avoidance"]
    for m in metrics:
        change = last[m] - first[m]
        arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
        print(f"  {m:<18}: {first[m]:>5.1f} → {last[m]:>5.1f}  {arrow} {change:+.1f}")

    # Recommendations based on trends
    print("\n" + "=" * 78)
    print("ACTIONABLE INSIGHTS")
    print("=" * 78)

    # Find weakest improving metric
    metric_changes = {m: last[m] - first[m] for m in metrics}
    weakest = min(metric_changes, key=metric_changes.get)

    recommendations = {
        "prompt_quality": "Write longer, more specific first prompts. Include file names and clear actions.",
        "session_focus": "Start with a clear goal. End sessions when stuck rather than continuing aimlessly.",
        "efficiency": "Aim for concrete output (file edits). Avoid exploratory chat sessions.",
        "error_avoidance": "Be more specific about what you want. Avoid ambiguous commands.",
    }

    print(f"\n🎯 Focus area: {weakest}")
    print(f"   {recommendations[weakest]}")

    # Productivity ratio
    total_productive = sum(s["productive_sessions"] for s in weekly_stats)
    total_sessions = sum(s["sessions"] for s in weekly_stats)
    prod_ratio = total_productive / total_sessions * 100 if total_sessions > 0 else 0

    print(f"\n📊 Productivity ratio: {total_productive}/{total_sessions} sessions ({prod_ratio:.0f}%) produced file edits")

    if prod_ratio < 30:
        print("   Goal: Aim for 50%+ sessions with concrete output.")

    # Export CSV
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            fieldnames = ["week", "sessions", "overall_score", "overall_stderr",
                          "prompt_quality", "session_focus", "efficiency",
                          "error_avoidance", "total_edits", "productive_sessions"]
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(weekly_stats)
        print(f"\n>>> TRENDS CSV: {args.csv.absolute()}")


if __name__ == "__main__":
    main()
