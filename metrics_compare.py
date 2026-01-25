#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
metrics_compare.py - Analyze and compare validation sprint metrics

Generates detailed reports showing which metrics moved between native and focused modes.

Usage:
    ./metrics_compare.py                    # Compare all sprints by mode
    ./metrics_compare.py <sprint1> <sprint2> # Compare specific sprints
    ./metrics_compare.py --report           # Generate markdown report
    ./metrics_compare.py --json             # Output raw JSON
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import statistics

from capture_schema import ValidationRecord, SprintSummary, PromptCapture, SessionOutcome


SPRINT_DIR = Path.home() / "ai_shell_logs" / "validation" / "sprints"
RECORDS_DIR = Path.home() / "ai_shell_logs" / "validation" / "records"


@dataclass
class MetricDelta:
    """Represents a change in a metric between two conditions."""
    name: str
    native_value: float
    focused_value: float
    delta: float
    delta_pct: float
    direction: str  # "improved", "declined", "unchanged"
    significance: str  # "high", "medium", "low", "none"
    interpretation: str


@dataclass
class ComparisonReport:
    """Complete comparison report between modes."""
    generated: str = ""
    native_sprints: List[str] = field(default_factory=list)
    focused_sprints: List[str] = field(default_factory=list)

    # Counts
    native_prompts: int = 0
    focused_prompts: int = 0
    native_sessions: int = 0
    focused_sessions: int = 0

    # Metric deltas
    prompt_metrics: List[MetricDelta] = field(default_factory=list)
    session_metrics: List[MetricDelta] = field(default_factory=list)
    efficiency_metrics: List[MetricDelta] = field(default_factory=list)

    # Key findings
    improvements: List[str] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    # Verdict
    verdict: str = ""
    confidence: str = ""
    recommendation: str = ""


def load_all_sprints() -> Dict[str, List[dict]]:
    """Load all sprints grouped by mode."""
    sprints_by_mode = {"native": [], "focused": []}

    for sprint_file in SPRINT_DIR.glob("*.json"):
        with open(sprint_file) as f:
            meta = json.load(f)
        mode = meta.get("mode", "unknown")
        if mode in sprints_by_mode:
            sprints_by_mode[mode].append(meta)

    return sprints_by_mode


def load_records_for_sprint(sprint_meta: dict) -> List[ValidationRecord]:
    """Load all validation records for a sprint."""
    records = []
    for record_id in sprint_meta.get("records", []):
        record_file = RECORDS_DIR / f"{record_id}.json"
        if record_file.exists():
            with open(record_file) as f:
                records.append(ValidationRecord.from_dict(json.load(f)))
    return records


def aggregate_by_mode(sprints_by_mode: Dict[str, List[dict]]) -> Tuple[SprintSummary, SprintSummary]:
    """Aggregate all sprints by mode into two summaries."""
    native_records = []
    focused_records = []

    for sprint in sprints_by_mode.get("native", []):
        native_records.extend(load_records_for_sprint(sprint))

    for sprint in sprints_by_mode.get("focused", []):
        focused_records.extend(load_records_for_sprint(sprint))

    native_summary = SprintSummary.from_records(native_records, "all_native")
    native_summary.mode = "native"

    focused_summary = SprintSummary.from_records(focused_records, "all_focused")
    focused_summary.mode = "focused"

    return native_summary, focused_summary


def calculate_significance(native_val: float, focused_val: float,
                          metric_type: str = "higher_better") -> str:
    """
    Calculate significance of a metric change.
    Returns: "high", "medium", "low", "none"
    """
    if native_val == 0 and focused_val == 0:
        return "none"

    if native_val == 0:
        # Can't calculate percentage change from zero
        if focused_val > 0:
            return "high" if metric_type == "higher_better" else "high"
        return "none"

    pct_change = abs(focused_val - native_val) / native_val * 100

    if pct_change >= 50:
        return "high"
    elif pct_change >= 20:
        return "medium"
    elif pct_change >= 5:
        return "low"
    return "none"


def create_metric_delta(name: str, native_val: float, focused_val: float,
                       higher_is_better: bool = True,
                       description: str = "") -> MetricDelta:
    """Create a MetricDelta with analysis."""
    delta = focused_val - native_val

    if native_val != 0:
        delta_pct = delta / native_val * 100
    elif focused_val != 0:
        delta_pct = 100.0  # From 0 to something
    else:
        delta_pct = 0.0

    # Determine direction
    if abs(delta) < 0.001:
        direction = "unchanged"
    elif (delta > 0 and higher_is_better) or (delta < 0 and not higher_is_better):
        direction = "improved"
    else:
        direction = "declined"

    significance = calculate_significance(native_val, focused_val)

    # Generate interpretation
    if direction == "unchanged":
        interpretation = f"{name} stayed the same"
    elif direction == "improved":
        if higher_is_better:
            interpretation = f"{name} increased by {abs(delta_pct):.1f}% (better)"
        else:
            interpretation = f"{name} decreased by {abs(delta_pct):.1f}% (better)"
    else:
        if higher_is_better:
            interpretation = f"{name} decreased by {abs(delta_pct):.1f}% (worse)"
        else:
            interpretation = f"{name} increased by {abs(delta_pct):.1f}% (worse)"

    if description:
        interpretation += f" - {description}"

    return MetricDelta(
        name=name,
        native_value=native_val,
        focused_value=focused_val,
        delta=delta,
        delta_pct=delta_pct,
        direction=direction,
        significance=significance,
        interpretation=interpretation
    )


def generate_comparison_report(native: SprintSummary, focused: SprintSummary) -> ComparisonReport:
    """Generate a comprehensive comparison report."""
    report = ComparisonReport(
        generated=datetime.now().isoformat(),
        native_prompts=native.total_prompts,
        focused_prompts=focused.total_prompts,
        native_sessions=native.total_sessions,
        focused_sessions=focused.total_sessions
    )

    # Prompt-level metrics
    report.prompt_metrics = [
        create_metric_delta(
            "Average Overall Score",
            native.avg_overall_score,
            focused.avg_overall_score,
            higher_is_better=True,
            description="Combined directive/scoped/actionable"
        ),
        create_metric_delta(
            "Average Directive Score",
            native.avg_directive_score,
            focused.avg_directive_score,
            higher_is_better=True,
            description="Clear, specific outcome stated"
        ),
        create_metric_delta(
            "Average Scoped Score",
            native.avg_scoped_score,
            focused.avg_scoped_score,
            higher_is_better=True,
            description="Limited to one task"
        ),
        create_metric_delta(
            "Average Actionable Score",
            native.avg_actionable_score,
            focused.avg_actionable_score,
            higher_is_better=True,
            description="Can begin work immediately"
        ),
        create_metric_delta(
            "Prompts Passed",
            native.prompts_passed_clinic / native.total_prompts * 100 if native.total_prompts else 0,
            focused.prompts_passed_clinic / focused.total_prompts * 100 if focused.total_prompts else 0,
            higher_is_better=True,
            description="Percentage scoring >= 7"
        ),
        create_metric_delta(
            "Prompts with Flags",
            native.prompts_with_flags / native.total_prompts * 100 if native.total_prompts else 0,
            focused.prompts_with_flags / focused.total_prompts * 100 if focused.total_prompts else 0,
            higher_is_better=False,
            description="Had research_leak, scope_creep, etc."
        ),
    ]

    # Session-level metrics (if we have outcome data)
    if native.total_sessions > 0 or focused.total_sessions > 0:
        report.session_metrics = [
            create_metric_delta(
                "Healthy Sessions",
                native.sessions_healthy / native.total_sessions * 100 if native.total_sessions else 0,
                focused.sessions_healthy / focused.total_sessions * 100 if focused.total_sessions else 0,
                higher_is_better=True,
                description="No errors, no dead ends"
            ),
            create_metric_delta(
                "Productive Sessions",
                native.sessions_productive / native.total_sessions * 100 if native.total_sessions else 0,
                focused.sessions_productive / focused.total_sessions * 100 if focused.total_sessions else 0,
                higher_is_better=True,
                description="Completed work effectively"
            ),
            create_metric_delta(
                "Struggling Sessions",
                native.sessions_struggling / native.total_sessions * 100 if native.total_sessions else 0,
                focused.sessions_struggling / focused.total_sessions * 100 if focused.total_sessions else 0,
                higher_is_better=False,
                description="High errors or dead ends"
            ),
        ]

    # Efficiency metrics
    report.efficiency_metrics = [
        create_metric_delta(
            "Tokens per Tool Call",
            native.avg_tokens_per_tool,
            focused.avg_tokens_per_tool,
            higher_is_better=False,
            description="Lower = more efficient"
        ),
        create_metric_delta(
            "Cache Hit Rate",
            native.avg_cache_rate,
            focused.avg_cache_rate,
            higher_is_better=True,
            description="Higher = better context reuse"
        ),
        create_metric_delta(
            "Todo Completion Rate",
            native.avg_todo_completion,
            focused.avg_todo_completion,
            higher_is_better=True,
            description="Tasks finished vs started"
        ),
        create_metric_delta(
            "Wasted Thinking",
            native.avg_wasted_thinking_pct,
            focused.avg_wasted_thinking_pct,
            higher_is_better=False,
            description="Thinking with no following action"
        ),
        create_metric_delta(
            "Total Errors",
            native.total_errors,
            focused.total_errors,
            higher_is_better=False,
            description="Errors encountered"
        ),
        create_metric_delta(
            "Dead Ends",
            native.total_dead_ends,
            focused.total_dead_ends,
            higher_is_better=False,
            description="Conversation dead ends"
        ),
    ]

    # Categorize findings
    all_metrics = report.prompt_metrics + report.session_metrics + report.efficiency_metrics

    for metric in all_metrics:
        if metric.direction == "improved" and metric.significance in ["high", "medium"]:
            report.improvements.append(metric.interpretation)
        elif metric.direction == "declined" and metric.significance in ["high", "medium"]:
            report.regressions.append(metric.interpretation)
        elif metric.significance == "none" or metric.direction == "unchanged":
            report.unchanged.append(metric.name)

    # Generate verdict
    improvement_count = len(report.improvements)
    regression_count = len(report.regressions)
    total_significant = improvement_count + regression_count

    if total_significant == 0:
        report.verdict = "NO SIGNIFICANT DIFFERENCE"
        report.confidence = "low"
        report.recommendation = "Need more data to draw conclusions"
    elif improvement_count > regression_count * 2:
        report.verdict = "FOCUSED MODE RECOMMENDED"
        report.confidence = "high" if improvement_count >= 3 else "medium"
        report.recommendation = f"Focused mode shows improvement in {improvement_count} key metrics"
    elif regression_count > improvement_count * 2:
        report.verdict = "NATIVE MODE PREFERRED"
        report.confidence = "high" if regression_count >= 3 else "medium"
        report.recommendation = f"Focused mode shows regression in {regression_count} key metrics"
    else:
        report.verdict = "MIXED RESULTS"
        report.confidence = "medium"
        report.recommendation = f"Trade-offs: {improvement_count} improvements, {regression_count} regressions"

    return report


def print_report_text(report: ComparisonReport):
    """Print report in human-readable format."""
    print("=" * 70)
    print("METRICS COMPARISON REPORT")
    print("=" * 70)
    print(f"Generated: {report.generated}")
    print()

    print("DATA SUMMARY")
    print("-" * 40)
    print(f"  Native mode:  {report.native_prompts} prompts, {report.native_sessions} sessions")
    print(f"  Focused mode: {report.focused_prompts} prompts, {report.focused_sessions} sessions")
    print()

    if report.prompt_metrics:
        print("PROMPT QUALITY METRICS")
        print("-" * 40)
        print(f"{'Metric':<30} {'Native':>10} {'Focused':>10} {'Delta':>10} {'Status':>12}")
        print("-" * 72)
        for m in report.prompt_metrics:
            status = f"[{m.direction.upper()}]" if m.significance != "none" else ""
            print(f"{m.name:<30} {m.native_value:>10.1f} {m.focused_value:>10.1f} {m.delta:>+10.1f} {status:>12}")
        print()

    if report.session_metrics:
        print("SESSION HEALTH METRICS")
        print("-" * 40)
        print(f"{'Metric':<30} {'Native':>10} {'Focused':>10} {'Delta':>10} {'Status':>12}")
        print("-" * 72)
        for m in report.session_metrics:
            status = f"[{m.direction.upper()}]" if m.significance != "none" else ""
            print(f"{m.name:<30} {m.native_value:>10.1f} {m.focused_value:>10.1f} {m.delta:>+10.1f} {status:>12}")
        print()

    if report.efficiency_metrics:
        print("EFFICIENCY METRICS")
        print("-" * 40)
        print(f"{'Metric':<30} {'Native':>10} {'Focused':>10} {'Delta':>10} {'Status':>12}")
        print("-" * 72)
        for m in report.efficiency_metrics:
            status = f"[{m.direction.upper()}]" if m.significance != "none" else ""
            print(f"{m.name:<30} {m.native_value:>10.1f} {m.focused_value:>10.1f} {m.delta:>+10.1f} {status:>12}")
        print()

    print("KEY FINDINGS")
    print("-" * 40)

    if report.improvements:
        print("\n  IMPROVEMENTS (Focused > Native):")
        for finding in report.improvements:
            print(f"    + {finding}")

    if report.regressions:
        print("\n  REGRESSIONS (Native > Focused):")
        for finding in report.regressions:
            print(f"    - {finding}")

    if report.unchanged and not report.improvements and not report.regressions:
        print("\n  UNCHANGED:")
        for name in report.unchanged[:5]:
            print(f"    = {name}")

    print()
    print("=" * 70)
    print(f"VERDICT: {report.verdict}")
    print(f"Confidence: {report.confidence}")
    print(f"Recommendation: {report.recommendation}")
    print("=" * 70)


def generate_markdown_report(report: ComparisonReport) -> str:
    """Generate a markdown report."""
    lines = [
        "# Validation Sprint Metrics Comparison",
        "",
        f"**Generated:** {report.generated}",
        "",
        "## Data Summary",
        "",
        "| Mode | Prompts | Sessions |",
        "|------|---------|----------|",
        f"| Native | {report.native_prompts} | {report.native_sessions} |",
        f"| Focused | {report.focused_prompts} | {report.focused_sessions} |",
        "",
    ]

    if report.prompt_metrics:
        lines.extend([
            "## Prompt Quality Metrics",
            "",
            "| Metric | Native | Focused | Delta | Status |",
            "|--------|--------|---------|-------|--------|",
        ])
        for m in report.prompt_metrics:
            status = m.direction.upper() if m.significance != "none" else "-"
            lines.append(f"| {m.name} | {m.native_value:.1f} | {m.focused_value:.1f} | {m.delta:+.1f} | {status} |")
        lines.append("")

    if report.session_metrics:
        lines.extend([
            "## Session Health Metrics",
            "",
            "| Metric | Native | Focused | Delta | Status |",
            "|--------|--------|---------|-------|--------|",
        ])
        for m in report.session_metrics:
            status = m.direction.upper() if m.significance != "none" else "-"
            lines.append(f"| {m.name} | {m.native_value:.1f} | {m.focused_value:.1f} | {m.delta:+.1f} | {status} |")
        lines.append("")

    if report.efficiency_metrics:
        lines.extend([
            "## Efficiency Metrics",
            "",
            "| Metric | Native | Focused | Delta | Status |",
            "|--------|--------|---------|-------|--------|",
        ])
        for m in report.efficiency_metrics:
            status = m.direction.upper() if m.significance != "none" else "-"
            lines.append(f"| {m.name} | {m.native_value:.1f} | {m.focused_value:.1f} | {m.delta:+.1f} | {status} |")
        lines.append("")

    lines.extend([
        "## Key Findings",
        "",
    ])

    if report.improvements:
        lines.append("### Improvements (Focused > Native)")
        lines.append("")
        for finding in report.improvements:
            lines.append(f"- {finding}")
        lines.append("")

    if report.regressions:
        lines.append("### Regressions (Native > Focused)")
        lines.append("")
        for finding in report.regressions:
            lines.append(f"- {finding}")
        lines.append("")

    lines.extend([
        "## Verdict",
        "",
        f"**{report.verdict}**",
        "",
        f"- Confidence: {report.confidence}",
        f"- Recommendation: {report.recommendation}",
        "",
    ])

    return "\n".join(lines)


def analyze_prompt_patterns(native_records: List[ValidationRecord],
                           focused_records: List[ValidationRecord]) -> dict:
    """Analyze patterns in prompt types and flags."""
    patterns = {
        "native": {"types": defaultdict(int), "flags": defaultdict(int), "fitness": defaultdict(int)},
        "focused": {"types": defaultdict(int), "flags": defaultdict(int), "fitness": defaultdict(int)}
    }

    for record in native_records:
        p = record.prompt
        patterns["native"]["types"][p.classification.type] += 1
        patterns["native"]["fitness"][p.classification.fitness] += 1
        for flag in p.flags.to_list():
            patterns["native"]["flags"][flag] += 1

    for record in focused_records:
        p = record.prompt
        patterns["focused"]["types"][p.classification.type] += 1
        patterns["focused"]["fitness"][p.classification.fitness] += 1
        for flag in p.flags.to_list():
            patterns["focused"]["flags"][flag] += 1

    return patterns


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Compare validation sprint metrics")
    parser.add_argument("sprint1", nargs="?", help="First sprint ID (optional)")
    parser.add_argument("sprint2", nargs="?", help="Second sprint ID (optional)")
    parser.add_argument("--report", action="store_true", help="Generate markdown report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", "-o", type=Path, help="Write report to file")
    args = parser.parse_args()

    # Load data
    sprints_by_mode = load_all_sprints()

    if not sprints_by_mode["native"] and not sprints_by_mode["focused"]:
        print("No sprints found. Run some sprints first.")
        print("  ./sprint_runner.py start native")
        print("  ./sprint_runner.py start focused")
        sys.exit(1)

    # Aggregate by mode
    native_summary, focused_summary = aggregate_by_mode(sprints_by_mode)

    # Store sprint IDs
    native_ids = [s["sprint_id"] for s in sprints_by_mode.get("native", [])]
    focused_ids = [s["sprint_id"] for s in sprints_by_mode.get("focused", [])]

    # Generate report
    report = generate_comparison_report(native_summary, focused_summary)
    report.native_sprints = native_ids
    report.focused_sprints = focused_ids

    # Output
    if args.json:
        # Convert to JSON-serializable format
        output = {
            "generated": report.generated,
            "native_sprints": report.native_sprints,
            "focused_sprints": report.focused_sprints,
            "native_prompts": report.native_prompts,
            "focused_prompts": report.focused_prompts,
            "native_sessions": report.native_sessions,
            "focused_sessions": report.focused_sessions,
            "prompt_metrics": [asdict(m) for m in report.prompt_metrics],
            "session_metrics": [asdict(m) for m in report.session_metrics],
            "efficiency_metrics": [asdict(m) for m in report.efficiency_metrics],
            "improvements": report.improvements,
            "regressions": report.regressions,
            "unchanged": report.unchanged,
            "verdict": report.verdict,
            "confidence": report.confidence,
            "recommendation": report.recommendation
        }
        print(json.dumps(output, indent=2))
    elif args.report or args.output:
        md = generate_markdown_report(report)
        if args.output:
            args.output.write_text(md)
            print(f"Report written to {args.output}")
        else:
            print(md)
    else:
        print_report_text(report)


if __name__ == "__main__":
    main()
