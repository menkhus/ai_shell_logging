#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
cache_behavior_report.py - Correlate user behavior with cache efficiency

The hypothesis: User behavior drives cache efficiency, not system config.

This tool identifies:
- Missed caching opportunities
- Anti-patterns that waste context
- Behavioral changes that would improve cache hit rates
- Cost savings from better behavior

Usage:
    ./cache_behavior_report.py                # Full report
    ./cache_behavior_report.py --csv out.csv  # Export opportunities
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
class CacheBehaviorSession:
    """Combined cache and behavior metrics for a session."""
    session_id: str
    project: str
    date: str

    # Cache metrics
    cache_read: int = 0
    cache_create: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_rate: float = 0.0
    estimated_cost: float = 0.0

    # Behavior metrics
    prompt_quality: float = 0.0
    session_focus: float = 0.0
    overall_score: float = 0.0
    duration_min: float = 0.0
    files_edited: int = 0

    # Prompt analysis
    first_prompt: str = ""
    anti_patterns: list = field(default_factory=list)

    # Derived
    wasted_cache: int = 0  # Cache created but session abandoned quickly
    cache_efficiency_score: float = 0.0

    def compute_derived(self):
        """Compute derived metrics."""
        # Wasted cache: created a lot but session was very short
        if self.duration_min < 5 and self.cache_create > 100000:
            self.wasted_cache = self.cache_create

        # Cache efficiency: combination of hit rate and utilization
        if self.cache_read + self.input_tokens > 0:
            hit_rate = self.cache_read / (self.cache_read + self.input_tokens)
        else:
            hit_rate = 0

        # Penalize for wasted cache creation
        waste_penalty = min(0.3, self.wasted_cache / 1e6 * 0.1)

        self.cache_efficiency_score = max(0, hit_rate * 100 - waste_penalty * 100)


@dataclass
class CachingOpportunity:
    """A missed opportunity for better caching."""
    opportunity_type: str
    severity: str  # high, medium, low
    description: str
    sessions_affected: list
    estimated_waste: float  # Tokens wasted
    recommendation: str


def load_and_join_data() -> list[CacheBehaviorSession]:
    """Load and join context and behavior data."""
    sessions = []

    # Try to load from CSVs first
    context_path = Path("context_metrics.csv")
    behavior_path = Path("user_behavior_scores.csv")

    if not context_path.exists() or not behavior_path.exists():
        print("Required CSVs not found. Run context_analysis.py and user_behavior_analysis.py first.")
        return []

    # Load context data
    context_data = {}
    with open(context_path) as f:
        for row in csv.DictReader(f):
            context_data[row["session_id"]] = row

    # Load behavior data
    behavior_data = {}
    with open(behavior_path) as f:
        for row in csv.DictReader(f):
            behavior_data[row["session_id"]] = row

    # Join
    for sid, ctx in context_data.items():
        beh = behavior_data.get(sid, {})

        session = CacheBehaviorSession(
            session_id=sid,
            project=ctx.get("project", ""),
            date=ctx.get("date", ""),
            cache_read=int(ctx.get("cache_read", 0) or 0),
            cache_create=int(ctx.get("cache_create", 0) or 0),
            input_tokens=int(ctx.get("input_tokens", 0) or 0),
            output_tokens=int(ctx.get("output_tokens", 0) or 0),
            cache_hit_rate=float(ctx.get("cache_hit_rate", 0) or 0),
            estimated_cost=float(ctx.get("estimated_cost", 0) or 0),
            duration_min=float(ctx.get("duration_min", 0) or 0),
            prompt_quality=float(beh.get("prompt_quality", 0) or 0),
            session_focus=float(beh.get("session_focus", 0) or 0),
            overall_score=float(beh.get("overall_score", 0) or 0),
            files_edited=int(beh.get("files_edited", 0) or 0),
            first_prompt=beh.get("first_prompt", ""),
            anti_patterns=beh.get("anti_patterns", "").split("; ") if beh.get("anti_patterns") else [],
        )
        session.compute_derived()
        sessions.append(session)

    return sessions


def identify_opportunities(sessions: list[CacheBehaviorSession]) -> list[CachingOpportunity]:
    """Identify missed caching opportunities."""
    opportunities = []

    # Group sessions by project and date
    by_project_date = defaultdict(list)
    for s in sessions:
        key = (s.project, s.date)
        by_project_date[key].append(s)

    # 1. Multiple sessions same day (could have continued)
    multi_session_days = []
    for (proj, date), day_sessions in by_project_date.items():
        if len(day_sessions) >= 2:
            total_cache_create = sum(s.cache_create for s in day_sessions)
            # After first session, subsequent sessions rebuild cache
            wasted = sum(s.cache_create for s in day_sessions[1:])
            if wasted > 500000:  # 500K+ tokens
                multi_session_days.append({
                    "project": proj,
                    "date": date,
                    "sessions": day_sessions,
                    "wasted": wasted,
                })

    if multi_session_days:
        total_wasted = sum(m["wasted"] for m in multi_session_days)
        affected = []
        for m in multi_session_days:
            affected.extend([s.session_id for s in m["sessions"][1:]])

        opportunities.append(CachingOpportunity(
            opportunity_type="multiple_sessions_same_day",
            severity="high",
            description=f"{len(multi_session_days)} days with multiple sessions that could have been continued",
            sessions_affected=affected,
            estimated_waste=total_wasted,
            recommendation="Continue existing sessions instead of starting new ones. Each new session rebuilds cache from scratch.",
        ))

    # 2. "Continue" without context
    continue_sessions = [s for s in sessions if "continue" in s.first_prompt.lower()]
    if continue_sessions:
        # These often have worse outcomes
        avg_score = statistics.mean(s.overall_score for s in continue_sessions)
        overall_avg = statistics.mean(s.overall_score for s in sessions) if sessions else 0

        if avg_score < overall_avg - 5:  # Notably worse
            opportunities.append(CachingOpportunity(
                opportunity_type="vague_continue",
                severity="medium",
                description=f"{len(continue_sessions)} sessions started with bare 'continue' (avg score: {avg_score:.0f} vs {overall_avg:.0f})",
                sessions_affected=[s.session_id for s in continue_sessions],
                estimated_waste=0,  # Hard to quantify
                recommendation="Instead of 'continue', provide context: 'Continue with X - we were working on Y'",
            ))

    # 3. Short sessions with high cache creation (abandoned)
    abandoned = [s for s in sessions if s.duration_min < 3 and s.cache_create > 200000]
    if abandoned:
        total_wasted = sum(s.cache_create for s in abandoned)
        opportunities.append(CachingOpportunity(
            opportunity_type="abandoned_sessions",
            severity="medium",
            description=f"{len(abandoned)} sessions <3min that created significant cache then stopped",
            sessions_affected=[s.session_id for s in abandoned],
            estimated_waste=total_wasted,
            recommendation="If starting a session, commit to at least 5-10 minutes of work. Quick questions don't need full sessions.",
        ))

    # 4. Low cache hit rate sessions
    low_cache = [s for s in sessions if s.cache_hit_rate < 50 and s.cache_read + s.input_tokens > 10000]
    if low_cache:
        opportunities.append(CachingOpportunity(
            opportunity_type="low_cache_hit",
            severity="low",
            description=f"{len(low_cache)} sessions with <50% cache hit rate",
            sessions_affected=[s.session_id for s in low_cache],
            estimated_waste=sum(s.input_tokens for s in low_cache),
            recommendation="These sessions rebuilt context from scratch. Check if they followed a session break >5 min.",
        ))

    # 5. Warmup/agent sessions (system overhead)
    warmup = [s for s in sessions if "warmup" in s.first_prompt.lower() or s.first_prompt.startswith("agent-")]
    if warmup:
        opportunities.append(CachingOpportunity(
            opportunity_type="system_overhead",
            severity="low",
            description=f"{len(warmup)} warmup/agent sessions (system overhead, not user behavior)",
            sessions_affected=[s.session_id for s in warmup],
            estimated_waste=sum(s.cache_create for s in warmup),
            recommendation="These are system sessions. No user action needed.",
        ))

    return opportunities


def compute_behavior_cache_correlation(sessions: list[CacheBehaviorSession]) -> dict:
    """Compute correlation between behavior scores and cache efficiency."""

    # Filter to sessions with enough data
    valid = [s for s in sessions if s.cache_read + s.input_tokens > 1000]

    if len(valid) < 10:
        return {"error": "insufficient data"}

    # Bucket by behavior
    good = [s for s in valid if s.overall_score >= 50]
    poor = [s for s in valid if s.overall_score < 50]

    results = {
        "good_behavior": {
            "n": len(good),
            "avg_cache_hit_rate": statistics.mean(s.cache_hit_rate for s in good) if good else 0,
            "avg_cost": statistics.mean(s.estimated_cost for s in good) if good else 0,
            "avg_files_edited": statistics.mean(s.files_edited for s in good) if good else 0,
        },
        "poor_behavior": {
            "n": len(poor),
            "avg_cache_hit_rate": statistics.mean(s.cache_hit_rate for s in poor) if poor else 0,
            "avg_cost": statistics.mean(s.estimated_cost for s in poor) if poor else 0,
            "avg_files_edited": statistics.mean(s.files_edited for s in poor) if poor else 0,
        },
    }

    # Compute Pearson correlation between behavior score and cache hit rate
    if len(valid) > 2:
        x = [s.overall_score for s in valid]
        y = [s.cache_hit_rate for s in valid]

        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        den_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

        if den_x > 0 and den_y > 0:
            results["correlation_behavior_cache"] = num / (den_x * den_y)
        else:
            results["correlation_behavior_cache"] = 0

    return results


def generate_report(sessions: list[CacheBehaviorSession], opportunities: list[CachingOpportunity]) -> str:
    """Generate the full report."""

    report = []
    report.append("=" * 75)
    report.append("CACHE EFFICIENCY vs USER BEHAVIOR REPORT")
    report.append("=" * 75)
    report.append(f"\nSessions analyzed: {len(sessions)}")

    # Summary stats
    total_cache_create = sum(s.cache_create for s in sessions)
    total_cache_read = sum(s.cache_read for s in sessions)
    total_cost = sum(s.estimated_cost for s in sessions)

    report.append(f"Total cache created: {total_cache_create/1e6:.1f}M tokens")
    report.append(f"Total cache read: {total_cache_read/1e6:.1f}M tokens")
    report.append(f"Total estimated cost: ${total_cost:.2f}")

    # Correlation analysis
    report.append("\n" + "-" * 75)
    report.append("BEHAVIOR → CACHE CORRELATION")
    report.append("-" * 75)

    corr = compute_behavior_cache_correlation(sessions)

    if "error" not in corr:
        report.append(f"\nGood behavior (score ≥50): {corr['good_behavior']['n']} sessions")
        report.append(f"  Avg cache hit rate: {corr['good_behavior']['avg_cache_hit_rate']:.1f}%")
        report.append(f"  Avg session cost: ${corr['good_behavior']['avg_cost']:.2f}")
        report.append(f"  Avg files edited: {corr['good_behavior']['avg_files_edited']:.1f}")

        report.append(f"\nPoor behavior (score <50): {corr['poor_behavior']['n']} sessions")
        report.append(f"  Avg cache hit rate: {corr['poor_behavior']['avg_cache_hit_rate']:.1f}%")
        report.append(f"  Avg session cost: ${corr['poor_behavior']['avg_cost']:.2f}")
        report.append(f"  Avg files edited: {corr['poor_behavior']['avg_files_edited']:.1f}")

        r = corr.get("correlation_behavior_cache", 0)
        report.append(f"\nCorrelation (behavior score ↔ cache hit rate): r = {r:.3f}")

        if r > 0.3:
            report.append("→ Positive correlation: Better behavior = better caching")
        elif r < -0.3:
            report.append("→ Negative correlation: Unexpected - investigate further")
        else:
            report.append("→ Weak correlation: Cache efficiency not strongly tied to behavior score")

    # Opportunities
    report.append("\n" + "=" * 75)
    report.append("MISSED CACHING OPPORTUNITIES")
    report.append("=" * 75)

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(key=lambda x: severity_order.get(x.severity, 3))

    total_waste = sum(o.estimated_waste for o in opportunities)
    waste_cost = total_waste / 1e6 * 3.75  # Cache creation cost

    report.append(f"\nTotal identified waste: {total_waste/1e6:.1f}M tokens (~${waste_cost:.2f})")

    for opp in opportunities:
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(opp.severity, "⚪")
        report.append(f"\n{severity_icon} [{opp.severity.upper()}] {opp.opportunity_type}")
        report.append(f"   {opp.description}")
        if opp.estimated_waste > 0:
            report.append(f"   Waste: {opp.estimated_waste/1e6:.1f}M tokens")
        report.append(f"   ✏️  {opp.recommendation}")

    # Top recommendations
    report.append("\n" + "=" * 75)
    report.append("TOP RECOMMENDATIONS FOR BETTER CACHING")
    report.append("=" * 75)

    report.append("""
1. 📋 CONTINUE SESSIONS, DON'T START NEW
   Each new session = full cache rebuild
   Cost: ~$0.004 per 1K tokens to rebuild vs $0.0003 to read from cache

2. 🚫 NEVER USE BARE 'continue'
   Bad:  "continue"
   Good: "Continue implementing the auth module - we added login, now add logout"

3. ⏱️ COMMIT TO 10+ MINUTE SESSIONS
   <5 min sessions waste cache creation
   Cache stays warm for ~5 minutes after last activity

4. 🔄 ONE SESSION PER TASK
   Multiple sessions same day = multiple cache rebuilds
   Use /clear within session if switching contexts

5. 💡 REFERENCE PRIOR CONTEXT
   "In the UserService we created earlier..."
   "Building on the test file from before..."
   This helps Claude retrieve cached context efficiently
""")

    # Behavior-specific recommendations
    report.append("\n" + "-" * 75)
    report.append("YOUR SPECIFIC PATTERNS")
    report.append("-" * 75)

    # Find user's worst patterns
    continue_count = len([s for s in sessions if "continue" in s.first_prompt.lower()])
    short_count = len([s for s in sessions if s.duration_min < 5])

    if continue_count > len(sessions) * 0.1:
        report.append(f"\n⚠️  You use bare 'continue' in {continue_count}/{len(sessions)} sessions ({continue_count/len(sessions)*100:.0f}%)")
        report.append("   Action: Add context to your continue prompts")

    if short_count > len(sessions) * 0.3:
        report.append(f"\n⚠️  {short_count}/{len(sessions)} sessions are <5 minutes ({short_count/len(sessions)*100:.0f}%)")
        report.append("   Action: Combine quick tasks into longer focused sessions")

    return "\n".join(report)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Correlate cache efficiency with user behavior")
    parser.add_argument("--csv", type=Path, help="Export opportunities as CSV")
    parser.add_argument("-o", "--output", type=Path, help="Save report to file")
    args = parser.parse_args()

    print("Loading and joining data...", end="", flush=True)
    sessions = load_and_join_data()
    print(f" found {len(sessions)} sessions")

    if not sessions:
        return 1

    print("Identifying opportunities...", end="", flush=True)
    opportunities = identify_opportunities(sessions)
    print(f" found {len(opportunities)} types")

    # Generate report
    report = generate_report(sessions, opportunities)

    if args.output:
        args.output.write_text(report)
        print(f"\n>>> REPORT: {args.output.absolute()}")
    else:
        print(report)

    # Export CSV
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            fieldnames = ["opportunity_type", "severity", "description",
                          "sessions_affected", "estimated_waste", "recommendation"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for opp in opportunities:
                writer.writerow({
                    "opportunity_type": opp.opportunity_type,
                    "severity": opp.severity,
                    "description": opp.description,
                    "sessions_affected": len(opp.sessions_affected),
                    "estimated_waste": opp.estimated_waste,
                    "recommendation": opp.recommendation,
                })
        print(f"\n>>> OPPORTUNITIES CSV: {args.csv.absolute()}")


if __name__ == "__main__":
    main()
