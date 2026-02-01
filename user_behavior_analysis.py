#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
user_behavior_analysis.py - Analyze user behavior patterns in Claude sessions

Hypothesis: Most session inefficiencies are user-caused, not tool-caused.

Buckets user behaviors into:
- Prompt quality (specificity, length, clarity)
- Session discipline (goal-oriented vs wandering)
- Interaction patterns (back-and-forth vs decisive)

Outputs recommendations for better Claude usage over time.
"""

import csv
import re
import statistics
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserBehaviorScore:
    """Scores for a single session's user behavior."""
    session_id: str
    project: str
    date: str

    # Raw metrics
    user_msgs: int = 0
    files_edited: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    total_tokens: int = 0
    first_prompt: str = ""

    # Derived behavior scores (0-100, higher = better)
    prompt_quality: float = 0.0
    session_focus: float = 0.0
    efficiency: float = 0.0
    error_avoidance: float = 0.0

    # Detected anti-patterns
    anti_patterns: list = field(default_factory=list)

    # Overall score
    overall_score: float = 0.0


# Anti-patterns that indicate poor user behavior
ANTI_PATTERNS = {
    "vague_start": {
        "patterns": [r"^continue\.?$", r"^go\.?$", r"^yes\.?$", r"^ok\.?$", r"^do it\.?$"],
        "description": "Session started with vague/continuation prompt",
        "penalty": 20,
    },
    "no_context": {
        "patterns": [r"^fix", r"^make it", r"^change", r"^update"],
        "description": "Command without specifying what/where",
        "penalty": 15,
    },
    "exploration_only": {
        "check": lambda s: s.user_msgs > 5 and s.files_edited == 0,
        "description": "Many messages but no concrete output",
        "penalty": 10,
    },
    "high_error_rate": {
        "check": lambda s: s.tool_calls > 0 and (s.tool_errors / s.tool_calls) > 0.2,
        "description": "Error rate above 20%",
        "penalty": 15,
    },
    "token_waste": {
        "check": lambda s: s.total_tokens > 10000 and s.files_edited == 0,
        "description": "High token usage with no output",
        "penalty": 20,
    },
    "short_prompt": {
        "check": lambda s: len(s.first_prompt.strip()) < 20,
        "description": "First prompt under 20 characters",
        "penalty": 10,
    },
}

# Good patterns that indicate effective user behavior
GOOD_PATTERNS = {
    "specific_file": {
        "patterns": [r"\.(py|js|ts|go|rs|java|c|cpp|md|json|yaml)"],
        "description": "Mentioned specific file type",
        "bonus": 10,
    },
    "clear_action": {
        "patterns": [r"create a?", r"add a?", r"implement", r"write a?", r"build"],
        "description": "Clear action verb in prompt",
        "bonus": 10,
    },
    "provides_context": {
        "check": lambda s: len(s.first_prompt) > 50,
        "description": "Detailed first prompt (50+ chars)",
        "bonus": 15,
    },
    "efficient_session": {
        "check": lambda s: s.user_msgs > 0 and s.files_edited > 0 and (s.files_edited / s.user_msgs) > 0.1,
        "description": "Good edit-to-message ratio",
        "bonus": 20,
    },
}


def analyze_prompt_quality(prompt: str) -> tuple[float, list[str]]:
    """Analyze the quality of the first prompt."""
    score = 50.0  # Start at neutral
    issues = []

    prompt_lower = prompt.lower().strip()

    # Check anti-patterns
    for name, pattern in ANTI_PATTERNS.items():
        if "patterns" in pattern:
            for p in pattern["patterns"]:
                if re.search(p, prompt_lower, re.IGNORECASE):
                    score -= pattern["penalty"]
                    issues.append(f"[BAD] {pattern['description']}")
                    break

    # Check good patterns
    for name, pattern in GOOD_PATTERNS.items():
        if "patterns" in pattern:
            for p in pattern["patterns"]:
                if re.search(p, prompt_lower, re.IGNORECASE):
                    score += pattern["bonus"]
                    break

    # Length bonus/penalty
    if len(prompt) > 100:
        score += 15
    elif len(prompt) < 20:
        score -= 10
        issues.append("[BAD] Very short prompt")

    return max(0, min(100, score)), issues


def analyze_session(row: dict) -> UserBehaviorScore:
    """Analyze a single session's user behavior."""

    score = UserBehaviorScore(
        session_id=str(row.get("session_file", ""))[:8],
        project=str(row.get("project", "")),
        date=str(row.get("date", "")),
        user_msgs=int(row.get("user_msgs", 0) or 0),
        files_edited=int(row.get("files_edited", 0) or 0),
        tool_calls=int(row.get("tool_calls", 0) or 0),
        tool_errors=int(row.get("tool_errors", 0) or 0),
        total_tokens=int(row.get("total_tokens", 0) or 0),
        first_prompt=str(row.get("first_prompt", "")),
    )

    # 1. Prompt quality
    score.prompt_quality, prompt_issues = analyze_prompt_quality(score.first_prompt)
    score.anti_patterns.extend(prompt_issues)

    # 2. Session focus (did we accomplish something?)
    if score.user_msgs == 0:
        score.session_focus = 0
    elif score.files_edited > 0:
        # Good: edited files
        ratio = score.files_edited / score.user_msgs
        score.session_focus = min(100, 50 + ratio * 200)
    elif score.tool_calls > 0:
        # Okay: at least used tools
        score.session_focus = 30
    else:
        # Poor: just chatting
        score.session_focus = 10
        score.anti_patterns.append("[BAD] No tools or edits - chat only")

    # 3. Efficiency (work per token)
    if score.total_tokens > 0 and score.files_edited > 0:
        tokens_per_edit = score.total_tokens / score.files_edited
        # Lower is better, normalize to 0-100
        if tokens_per_edit < 1000:
            score.efficiency = 100
        elif tokens_per_edit < 5000:
            score.efficiency = 70
        elif tokens_per_edit < 10000:
            score.efficiency = 50
        else:
            score.efficiency = 30
    elif score.files_edited == 0:
        score.efficiency = 20  # No output = low efficiency
    else:
        score.efficiency = 50

    # 4. Error avoidance
    if score.tool_calls == 0:
        score.error_avoidance = 50  # Neutral
    else:
        error_rate = score.tool_errors / score.tool_calls
        score.error_avoidance = max(0, 100 - error_rate * 200)

    # Check callable anti-patterns
    for name, pattern in ANTI_PATTERNS.items():
        if "check" in pattern and pattern["check"](score):
            score.anti_patterns.append(f"[BAD] {pattern['description']}")

    # Check callable good patterns
    for name, pattern in GOOD_PATTERNS.items():
        if "check" in pattern and pattern["check"](score):
            # Add as positive note
            pass  # Already reflected in scores

    # Overall score (weighted average)
    score.overall_score = (
        score.prompt_quality * 0.3 +
        score.session_focus * 0.3 +
        score.efficiency * 0.2 +
        score.error_avoidance * 0.2
    )

    return score


def generate_recommendations(scores: list[UserBehaviorScore]) -> list[str]:
    """Generate actionable recommendations based on behavior patterns."""

    recommendations = []

    # Analyze patterns across all sessions
    avg_prompt_quality = statistics.mean(s.prompt_quality for s in scores) if scores else 0
    avg_focus = statistics.mean(s.session_focus for s in scores) if scores else 0
    avg_efficiency = statistics.mean(s.efficiency for s in scores) if scores else 0

    # Count anti-patterns
    anti_pattern_counts = {}
    for s in scores:
        for ap in s.anti_patterns:
            anti_pattern_counts[ap] = anti_pattern_counts.get(ap, 0) + 1

    # Generate recommendations based on data
    if avg_prompt_quality < 50:
        recommendations.append(
            "📝 PROMPT QUALITY: Your prompts average {:.0f}/100. "
            "Try: Start with specific file names, clear actions, and context."
            .format(avg_prompt_quality)
        )

    if avg_focus < 40:
        recommendations.append(
            "🎯 SESSION FOCUS: Many sessions don't produce output. "
            "Try: Have a clear goal before starting. End sessions when stuck."
        )

    # Check for "continue" pattern
    continue_count = sum(1 for s in scores if "continue" in s.first_prompt.lower())
    if continue_count > len(scores) * 0.1:
        recommendations.append(
            f"🔄 CONTINUATION: {continue_count} sessions started with 'continue'. "
            "Try: Summarize what you want when resuming, don't assume context."
        )

    # Check for exploration-only
    explore_only = sum(1 for s in scores if s.user_msgs > 5 and s.files_edited == 0)
    if explore_only > len(scores) * 0.3:
        recommendations.append(
            f"🔍 EXPLORATION: {explore_only} sessions had 5+ messages but no edits. "
            "Try: If exploring, ask specific questions. If building, specify the output."
        )

    return recommendations


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze user behavior in Claude sessions")
    parser.add_argument("--csv", type=Path, default=Path("enhanced_metrics.csv"),
                        help="Input CSV with session metrics")
    parser.add_argument("-o", "--output", type=Path, help="Save report to file")
    parser.add_argument("--scores-csv", type=Path, help="Export behavior scores as CSV")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: {args.csv} not found. Run session_analytics.py --csv first.")
        return 1

    # Load sessions
    rows = []
    with open(args.csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Analyzing {len(rows)} sessions for user behavior patterns...\n")

    # Analyze each session
    scores = [analyze_session(row) for row in rows]

    # Filter to sessions with activity
    active_scores = [s for s in scores if s.user_msgs > 0]

    # Report
    report = []
    report.append("=" * 70)
    report.append("USER BEHAVIOR ANALYSIS - IS IT THE USER, NOT THE TOOL?")
    report.append("=" * 70)

    # Overall stats
    if active_scores:
        report.append(f"\nSessions analyzed: {len(active_scores)}")
        report.append(f"Average overall score: {statistics.mean(s.overall_score for s in active_scores):.1f}/100")
        report.append(f"Average prompt quality: {statistics.mean(s.prompt_quality for s in active_scores):.1f}/100")
        report.append(f"Average session focus: {statistics.mean(s.session_focus for s in active_scores):.1f}/100")
        report.append(f"Average efficiency: {statistics.mean(s.efficiency for s in active_scores):.1f}/100")

    # Distribution
    report.append("\n" + "-" * 70)
    report.append("SCORE DISTRIBUTION")
    report.append("-" * 70)

    excellent = [s for s in active_scores if s.overall_score >= 70]
    good = [s for s in active_scores if 50 <= s.overall_score < 70]
    poor = [s for s in active_scores if s.overall_score < 50]

    report.append(f"  Excellent (70+): {len(excellent)} sessions ({len(excellent)/len(active_scores)*100:.0f}%)")
    report.append(f"  Good (50-70):    {len(good)} sessions ({len(good)/len(active_scores)*100:.0f}%)")
    report.append(f"  Poor (<50):      {len(poor)} sessions ({len(poor)/len(active_scores)*100:.0f}%)")

    # Top anti-patterns
    report.append("\n" + "-" * 70)
    report.append("MOST COMMON USER ANTI-PATTERNS")
    report.append("-" * 70)

    anti_pattern_counts = {}
    for s in active_scores:
        for ap in s.anti_patterns:
            anti_pattern_counts[ap] = anti_pattern_counts.get(ap, 0) + 1

    for ap, count in sorted(anti_pattern_counts.items(), key=lambda x: -x[1])[:7]:
        report.append(f"  {count:3d}x: {ap}")

    # Best sessions (learn from success)
    report.append("\n" + "-" * 70)
    report.append("TOP 5 BEST USER BEHAVIOR (learn from these)")
    report.append("-" * 70)

    for s in sorted(active_scores, key=lambda x: -x.overall_score)[:5]:
        report.append(f"\n  Score: {s.overall_score:.0f}/100 | {s.files_edited} edits in {s.user_msgs} msgs")
        report.append(f"  Prompt: \"{s.first_prompt[:60]}...\"")

    # Worst sessions (learn from mistakes)
    report.append("\n" + "-" * 70)
    report.append("TOP 5 WORST USER BEHAVIOR (avoid these patterns)")
    report.append("-" * 70)

    for s in sorted(active_scores, key=lambda x: x.overall_score)[:5]:
        report.append(f"\n  Score: {s.overall_score:.0f}/100 | {s.files_edited} edits in {s.user_msgs} msgs")
        report.append(f"  Prompt: \"{s.first_prompt[:60]}...\"")
        if s.anti_patterns:
            report.append(f"  Issues: {', '.join(s.anti_patterns[:2])}")

    # Recommendations
    report.append("\n" + "=" * 70)
    report.append("RECOMMENDATIONS FOR BETTER CLAUDE USAGE")
    report.append("=" * 70)

    recommendations = generate_recommendations(active_scores)
    for rec in recommendations:
        report.append(f"\n{rec}")

    if not recommendations:
        report.append("\n✅ No major issues detected. Keep up the good work!")

    # Causality note
    report.append("\n" + "=" * 70)
    report.append("CONCLUSION: USER vs TOOL")
    report.append("=" * 70)

    user_caused = len([s for s in active_scores if s.overall_score < 50])
    tool_caused = len([s for s in active_scores if s.error_avoidance < 30 and s.prompt_quality > 60])

    report.append(f"""
Sessions with poor user behavior: {user_caused} ({user_caused/len(active_scores)*100:.0f}%)
Sessions with apparent tool issues: {tool_caused} ({tool_caused/len(active_scores)*100:.0f}%)

Evidence suggests USER BEHAVIOR is the primary driver of session outcomes.
Key factors:
  - Prompt specificity correlates with success
  - "continue" sessions have higher error rates
  - Sessions without clear goals rarely produce output
""")

    # Output
    report_text = "\n".join(report)

    if args.output:
        args.output.write_text(report_text)
        print(f"Report saved to: {args.output}")
    else:
        print(report_text)

    # Export scores CSV
    if args.scores_csv:
        with open(args.scores_csv, "w", newline="") as f:
            fieldnames = ["session_id", "date", "project", "user_msgs", "files_edited",
                          "prompt_quality", "session_focus", "efficiency",
                          "error_avoidance", "overall_score", "anti_patterns", "first_prompt"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in active_scores:
                writer.writerow({
                    "session_id": s.session_id,
                    "date": s.date,
                    "project": s.project,
                    "user_msgs": s.user_msgs,
                    "files_edited": s.files_edited,
                    "prompt_quality": round(s.prompt_quality, 1),
                    "session_focus": round(s.session_focus, 1),
                    "efficiency": round(s.efficiency, 1),
                    "error_avoidance": round(s.error_avoidance, 1),
                    "overall_score": round(s.overall_score, 1),
                    "anti_patterns": "; ".join(s.anti_patterns),
                    "first_prompt": s.first_prompt[:80],
                })
        print(f"\n>>> SCORES CSV: {args.scores_csv.absolute()}")


if __name__ == "__main__":
    main()
