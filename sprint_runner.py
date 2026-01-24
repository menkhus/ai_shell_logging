#!/usr/bin/env python3
"""
sprint_runner.py - Run validation sprints and capture prompt/outcome data

Usage:
    # Start a native mode sprint
    ./sprint_runner.py start native

    # Start a focused mode sprint (with prompt clinic)
    ./sprint_runner.py start focused

    # Capture a prompt during sprint
    ./sprint_runner.py capture "your prompt here"

    # End sprint and generate report
    ./sprint_runner.py end

    # Link session outcomes after sessions complete
    ./sprint_runner.py link-outcomes

    # Compare two sprints
    ./sprint_runner.py compare <sprint_id_1> <sprint_id_2>

    # List all sprints
    ./sprint_runner.py list
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from capture_schema import (
    PromptCapture, SessionOutcome, ValidationRecord,
    SprintSummary, PromptScores, PromptFlags, PromptClassification
)


SPRINT_DIR = Path.home() / "ai_shell_logs" / "validation" / "sprints"
RECORDS_DIR = Path.home() / "ai_shell_logs" / "validation" / "records"
STATE_FILE = Path.home() / "ai_shell_logs" / "validation" / ".sprint_state"


def ensure_dirs():
    """Ensure validation directories exist."""
    SPRINT_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)


def get_active_sprint() -> Optional[dict]:
    """Get the currently active sprint, if any."""
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        if state.get("active"):
            return state
    except:
        pass
    return None


def set_active_sprint(sprint_id: str, mode: str):
    """Set the active sprint."""
    ensure_dirs()
    state = {
        "active": True,
        "sprint_id": sprint_id,
        "mode": mode,
        "started": datetime.now().isoformat(),
        "prompt_count": 0
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
    return state


def clear_active_sprint():
    """Clear the active sprint."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def update_sprint_state(updates: dict):
    """Update the active sprint state."""
    state = get_active_sprint()
    if state:
        state.update(updates)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)


def get_current_session_id() -> Optional[str]:
    """
    Get the current Claude Code session ID.
    Looks at the most recently modified JSONL in ~/.claude/projects/
    """
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        return None

    # Find most recent JSONL
    newest = None
    newest_time = 0
    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            mtime = jsonl.stat().st_mtime
            if mtime > newest_time:
                newest_time = mtime
                newest = jsonl

    if newest:
        # Extract session ID from first line
        try:
            with open(newest) as f:
                first_line = f.readline()
                entry = json.loads(first_line)
                return entry.get("sessionId")
        except:
            pass
    return None


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_start(mode: str):
    """Start a new validation sprint."""
    if mode not in ["native", "focused"]:
        print(f"Error: mode must be 'native' or 'focused', got '{mode}'")
        sys.exit(1)

    active = get_active_sprint()
    if active:
        print(f"Error: Sprint already active: {active['sprint_id']}")
        print(f"Run './sprint_runner.py end' to end it first.")
        sys.exit(1)

    sprint_id = f"sprint_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    state = set_active_sprint(sprint_id, mode)

    print(f"Started {mode.upper()} mode sprint: {sprint_id}")
    print()
    print("=" * 60)
    if mode == "native":
        print("NATIVE MODE - Work naturally, no intervention")
        print()
        print("Instructions:")
        print("  1. Work as you normally would with Claude Code")
        print("  2. Before each prompt, run:")
        print("     ./sprint_runner.py capture \"your prompt\"")
        print("  3. Or use the shell function: sprint_capture \"prompt\"")
        print("  4. When done, run: ./sprint_runner.py end")
    else:
        print("FOCUSED MODE - Use prompt clinic before each prompt")
        print()
        print("Instructions:")
        print("  1. Before each prompt, run prompt_clinic.sh first")
        print("  2. Use rewrites if suggested")
        print("  3. Then capture: ./sprint_runner.py capture \"prompt\"")
        print("  4. Track if you used the rewrite: --rewrite-used")
        print("  5. When done, run: ./sprint_runner.py end")
    print("=" * 60)

    # Create sprint metadata file
    sprint_meta = {
        "sprint_id": sprint_id,
        "mode": mode,
        "started": state["started"],
        "records": []
    }
    sprint_file = SPRINT_DIR / f"{sprint_id}.json"
    with open(sprint_file, 'w') as f:
        json.dump(sprint_meta, f, indent=2)

    print(f"\nSprint file: {sprint_file}")


def cmd_capture(prompt_text: str, rewrite_used: bool = False,
                rewrite_text: str = "", notes: str = ""):
    """Capture a prompt during an active sprint."""
    active = get_active_sprint()
    if not active:
        print("Error: No active sprint. Run './sprint_runner.py start <mode>' first.")
        sys.exit(1)

    sprint_id = active["sprint_id"]
    mode = active["mode"]
    session_id = get_current_session_id() or f"unknown_{datetime.now().strftime('%H%M%S')}"

    # Create prompt capture
    capture = PromptCapture(
        session_id=session_id,
        mode=mode,
        prompt_text=prompt_text
    )
    capture.analyze()

    # In focused mode, run prompt clinic
    if mode == "focused":
        capture.run_prompt_clinic()

    # Track rewrite usage
    if rewrite_used and rewrite_text:
        capture.rewrite_suggested = True
        capture.rewrite_text = rewrite_text
        capture.rewrite_used = True
        capture.sent_as_is = False
        capture.final_prompt_text = rewrite_text
    elif rewrite_text:
        capture.rewrite_suggested = True
        capture.rewrite_text = rewrite_text
        capture.rewrite_used = False

    # Create validation record
    record = ValidationRecord(
        mode=mode,
        sprint_id=sprint_id,
        prompt=capture,
        user_notes=notes
    )

    # Save record
    record_file = record.save(RECORDS_DIR)

    # Update sprint metadata
    sprint_file = SPRINT_DIR / f"{sprint_id}.json"
    with open(sprint_file) as f:
        sprint_meta = json.load(f)
    sprint_meta["records"].append(record.record_id)
    with open(sprint_file, 'w') as f:
        json.dump(sprint_meta, f, indent=2)

    # Update state
    update_sprint_state({"prompt_count": active["prompt_count"] + 1})

    # Display capture summary
    print(f"Captured prompt #{active['prompt_count'] + 1}")
    print(f"  Type: {capture.classification.type}")
    print(f"  Fitness: {capture.classification.fitness}")
    if capture.flags.any_flags:
        print(f"  Flags: {', '.join(capture.flags.to_list())}")
    if mode == "focused" and capture.scores.overall > 0:
        status = "PASS" if capture.scores.passed else "FAIL"
        print(f"  Score: {capture.scores.overall}/10 ({status})")
    print(f"  Record: {record.record_id}")


def cmd_end():
    """End the active sprint and generate summary."""
    active = get_active_sprint()
    if not active:
        print("Error: No active sprint.")
        sys.exit(1)

    sprint_id = active["sprint_id"]
    sprint_file = SPRINT_DIR / f"{sprint_id}.json"

    # Load sprint metadata
    with open(sprint_file) as f:
        sprint_meta = json.load(f)

    # Update with end time
    sprint_meta["ended"] = datetime.now().isoformat()
    sprint_meta["prompt_count"] = len(sprint_meta["records"])

    # Load all records
    records = []
    for record_id in sprint_meta["records"]:
        record_file = RECORDS_DIR / f"{record_id}.json"
        if record_file.exists():
            with open(record_file) as f:
                records.append(ValidationRecord.from_dict(json.load(f)))

    # Generate summary
    summary = SprintSummary.from_records(records, sprint_id)
    sprint_meta["summary"] = {
        "total_prompts": summary.total_prompts,
        "prompts_with_flags": summary.prompts_with_flags,
        "avg_overall_score": summary.avg_overall_score,
        "type_distribution": summary.type_distribution,
        "fitness_distribution": summary.fitness_distribution
    }

    # Save updated sprint metadata
    with open(sprint_file, 'w') as f:
        json.dump(sprint_meta, f, indent=2)

    # Clear active sprint
    clear_active_sprint()

    # Print summary
    print(f"Sprint ended: {sprint_id}")
    print("=" * 60)
    print(f"Mode: {active['mode'].upper()}")
    print(f"Duration: {active['started']} to {sprint_meta['ended']}")
    print(f"Prompts captured: {summary.total_prompts}")
    print()
    print("Prompt Analysis:")
    print(f"  With flags: {summary.prompts_with_flags}")
    if summary.avg_overall_score > 0:
        print(f"  Avg score: {summary.avg_overall_score:.1f}/10")
    print()
    print("Type distribution:")
    for ptype, count in sorted(summary.type_distribution.items(), key=lambda x: -x[1]):
        print(f"  {ptype}: {count}")
    print()
    print("Fitness distribution:")
    for fitness, count in sorted(summary.fitness_distribution.items(), key=lambda x: -x[1]):
        print(f"  {fitness}: {count}")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Run: ./sprint_runner.py link-outcomes")
    print("     (after sessions have completed)")
    print("  2. Run: ./sprint_runner.py compare <sprint1> <sprint2>")
    print("     (to compare native vs focused)")


def cmd_link_outcomes(sprint_id: str = None):
    """Link session outcomes to validation records."""
    # Find sprint to process
    if sprint_id:
        sprint_file = SPRINT_DIR / f"{sprint_id}.json"
        if not sprint_file.exists():
            print(f"Error: Sprint not found: {sprint_id}")
            sys.exit(1)
        sprints_to_process = [sprint_file]
    else:
        # Process all sprints without linked outcomes
        sprints_to_process = list(SPRINT_DIR.glob("*.json"))

    # Load extractor data once
    extractor_data = None
    extractor_export = Path.home() / "ai_shell_logs" / "extractor_export.json"

    # Run enhanced_extractor if export doesn't exist or is stale
    project_root = Path(__file__).parent
    extractor_script = project_root / "data_tool" / "enhanced_extractor.py"

    if extractor_script.exists():
        print("Running enhanced_extractor.py to get latest session data...")
        import subprocess
        try:
            subprocess.run(
                ["python3", str(extractor_script), "--export", str(extractor_export)],
                capture_output=True,
                timeout=120
            )
        except Exception as e:
            print(f"Warning: Could not run extractor: {e}")

    if extractor_export.exists():
        with open(extractor_export) as f:
            extractor_data = json.load(f)

    linked_count = 0
    for sprint_file in sprints_to_process:
        with open(sprint_file) as f:
            sprint_meta = json.load(f)

        for record_id in sprint_meta.get("records", []):
            record_file = RECORDS_DIR / f"{record_id}.json"
            if not record_file.exists():
                continue

            with open(record_file) as f:
                record_data = json.load(f)

            # Skip if already has outcome
            if record_data.get("outcome"):
                continue

            # Try to link outcome
            session_id = record_data.get("prompt", {}).get("session_id", "")
            if session_id and extractor_data:
                outcome = SessionOutcome.from_session(session_id, extractor_data)
                if outcome.turns > 0:  # Has data
                    record = ValidationRecord.from_dict(record_data)
                    record.outcome = outcome

                    # Save updated record
                    with open(record_file, 'w') as f:
                        json.dump(record.to_dict(), f, indent=2)

                    linked_count += 1
                    print(f"  Linked: {record_id} -> {session_id[:8]}...")

    print(f"\nLinked {linked_count} session outcomes.")


def cmd_compare(sprint_id_1: str, sprint_id_2: str):
    """Compare two sprints."""
    def load_sprint_summary(sprint_id: str) -> SprintSummary:
        sprint_file = SPRINT_DIR / f"{sprint_id}.json"
        if not sprint_file.exists():
            # Try partial match
            matches = list(SPRINT_DIR.glob(f"*{sprint_id}*.json"))
            if matches:
                sprint_file = matches[0]
            else:
                print(f"Error: Sprint not found: {sprint_id}")
                sys.exit(1)

        with open(sprint_file) as f:
            sprint_meta = json.load(f)

        # Load records
        records = []
        for record_id in sprint_meta.get("records", []):
            record_file = RECORDS_DIR / f"{record_id}.json"
            if record_file.exists():
                with open(record_file) as f:
                    records.append(ValidationRecord.from_dict(json.load(f)))

        return SprintSummary.from_records(records, sprint_meta["sprint_id"])

    summary1 = load_sprint_summary(sprint_id_1)
    summary2 = load_sprint_summary(sprint_id_2)

    # Compare
    delta = summary1.compare(summary2)

    print("=" * 70)
    print("SPRINT COMPARISON")
    print("=" * 70)
    print(f"\n  Sprint 1: {summary1.sprint_id} ({summary1.mode})")
    print(f"  Sprint 2: {summary2.sprint_id} ({summary2.mode})")
    print()

    print("PROMPT QUALITY (higher = better):")
    print(f"  Avg overall score:    {summary1.avg_overall_score:.1f} vs {summary2.avg_overall_score:.1f}  (delta: {delta['delta_avg_overall_score']:+.1f})")
    print(f"  Prompts passed:       {summary1.prompts_passed_clinic}/{summary1.total_prompts} vs {summary2.prompts_passed_clinic}/{summary2.total_prompts}  (delta: {delta['delta_prompts_passed_pct']:+.1f}%)")
    print()

    print("SESSION HEALTH (higher = better):")
    print(f"  Healthy sessions:     {summary1.sessions_healthy}/{summary1.total_sessions} vs {summary2.sessions_healthy}/{summary2.total_sessions}  (delta: {delta['delta_healthy_pct']:+.1f}%)")
    print(f"  Productive sessions:  {summary1.sessions_productive}/{summary1.total_sessions} vs {summary2.sessions_productive}/{summary2.total_sessions}  (delta: {delta['delta_productive_pct']:+.1f}%)")
    print()

    print("EFFICIENCY (positive delta = sprint 1 better):")
    print(f"  Tokens per tool:      {summary1.avg_tokens_per_tool:.0f} vs {summary2.avg_tokens_per_tool:.0f}  (delta: {delta['delta_tokens_per_tool']:+.0f})")
    print(f"  Cache rate:           {summary1.avg_cache_rate:.1f}% vs {summary2.avg_cache_rate:.1f}%  (delta: {delta['delta_cache_rate']:+.1f}%)")
    print(f"  Todo completion:      {summary1.avg_todo_completion:.1f}% vs {summary2.avg_todo_completion:.1f}%  (delta: {delta['delta_todo_completion']:+.1f}%)")
    print(f"  Wasted thinking:      {summary1.avg_wasted_thinking_pct:.1f}% vs {summary2.avg_wasted_thinking_pct:.1f}%  (delta: {delta['delta_wasted_thinking']:+.1f}%)")
    print()

    print("ERRORS (lower = better, positive delta = sprint 1 better):")
    print(f"  Total errors:         {summary1.total_errors} vs {summary2.total_errors}  (delta: {delta['delta_errors']:+d})")
    print(f"  Dead ends:            {summary1.total_dead_ends} vs {summary2.total_dead_ends}  (delta: {delta['delta_dead_ends']:+d})")
    print()

    print("SUBJECTIVE (higher = better):")
    print(f"  Felt productive:      {summary1.felt_productive_count}/{summary1.total_sessions} vs {summary2.felt_productive_count}/{summary2.total_sessions}  (delta: {delta['delta_felt_productive_pct']:+.1f}%)")
    print()

    # Overall verdict
    positive_deltas = sum(1 for k, v in delta.items() if k.startswith("delta_") and v > 0)
    negative_deltas = sum(1 for k, v in delta.items() if k.startswith("delta_") and v < 0)

    print("=" * 70)
    if positive_deltas > negative_deltas:
        winner = summary1.mode
        print(f"VERDICT: {summary1.mode.upper()} mode shows improvement in {positive_deltas}/{positive_deltas + negative_deltas} metrics")
    elif negative_deltas > positive_deltas:
        winner = summary2.mode
        print(f"VERDICT: {summary2.mode.upper()} mode shows improvement in {negative_deltas}/{positive_deltas + negative_deltas} metrics")
    else:
        print("VERDICT: No clear winner - modes are roughly equivalent")
    print("=" * 70)


def cmd_list():
    """List all sprints."""
    ensure_dirs()
    sprints = list(SPRINT_DIR.glob("*.json"))

    if not sprints:
        print("No sprints found.")
        print("Start one with: ./sprint_runner.py start <native|focused>")
        return

    print("=" * 70)
    print("VALIDATION SPRINTS")
    print("=" * 70)

    for sprint_file in sorted(sprints, key=lambda x: x.stat().st_mtime, reverse=True):
        with open(sprint_file) as f:
            meta = json.load(f)

        status = "completed" if meta.get("ended") else "active"
        print(f"\n  {meta['sprint_id']}")
        print(f"    Mode:    {meta['mode']}")
        print(f"    Status:  {status}")
        print(f"    Started: {meta['started']}")
        if meta.get("ended"):
            print(f"    Ended:   {meta['ended']}")
        print(f"    Records: {len(meta.get('records', []))}")

    print()

    # Show active sprint if any
    active = get_active_sprint()
    if active:
        print(f"Active sprint: {active['sprint_id']}")
        print(f"  Prompts captured: {active['prompt_count']}")


def cmd_status():
    """Show current sprint status."""
    active = get_active_sprint()
    if not active:
        print("No active sprint.")
        print("Start one with: ./sprint_runner.py start <native|focused>")
        return

    print(f"Active sprint: {active['sprint_id']}")
    print(f"  Mode: {active['mode']}")
    print(f"  Started: {active['started']}")
    print(f"  Prompts captured: {active['prompt_count']}")


# =============================================================================
# SHELL INTEGRATION
# =============================================================================

def print_shell_functions():
    """Print shell functions for easier capture."""
    print("""
# Add to your .zshrc or .bashrc for easier sprint capture:

sprint_capture() {
    python3 ~/src/ai_shell_logging/sprint_runner.py capture "$@"
}

sprint_start() {
    python3 ~/src/ai_shell_logging/sprint_runner.py start "$@"
}

sprint_end() {
    python3 ~/src/ai_shell_logging/sprint_runner.py end
}

sprint_status() {
    python3 ~/src/ai_shell_logging/sprint_runner.py status
}
""")


# =============================================================================
# MAIN
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run validation sprints and capture prompt/outcome data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./sprint_runner.py start native     Start a native mode sprint
  ./sprint_runner.py capture "fix bug"  Capture a prompt
  ./sprint_runner.py end              End sprint and generate summary
  ./sprint_runner.py link-outcomes    Link session data to records
  ./sprint_runner.py compare s1 s2    Compare two sprints
  ./sprint_runner.py list             List all sprints
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # start
    start_p = subparsers.add_parser("start", help="Start a new sprint")
    start_p.add_argument("mode", choices=["native", "focused"], help="Sprint mode")

    # capture
    capture_p = subparsers.add_parser("capture", help="Capture a prompt")
    capture_p.add_argument("prompt", help="The prompt text")
    capture_p.add_argument("--rewrite-used", action="store_true", help="Used a rewrite from prompt clinic")
    capture_p.add_argument("--rewrite", type=str, default="", help="The rewrite text if suggested")
    capture_p.add_argument("--notes", type=str, default="", help="Optional notes")

    # end
    subparsers.add_parser("end", help="End the active sprint")

    # link-outcomes
    link_p = subparsers.add_parser("link-outcomes", help="Link session outcomes to records")
    link_p.add_argument("sprint_id", nargs="?", help="Specific sprint to process")

    # compare
    compare_p = subparsers.add_parser("compare", help="Compare two sprints")
    compare_p.add_argument("sprint1", help="First sprint ID")
    compare_p.add_argument("sprint2", help="Second sprint ID")

    # list
    subparsers.add_parser("list", help="List all sprints")

    # status
    subparsers.add_parser("status", help="Show current sprint status")

    # shell
    subparsers.add_parser("shell", help="Print shell helper functions")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args.mode)
    elif args.command == "capture":
        cmd_capture(args.prompt, args.rewrite_used, args.rewrite, args.notes)
    elif args.command == "end":
        cmd_end()
    elif args.command == "link-outcomes":
        cmd_link_outcomes(args.sprint_id)
    elif args.command == "compare":
        cmd_compare(args.sprint1, args.sprint2)
    elif args.command == "list":
        cmd_list()
    elif args.command == "status":
        cmd_status()
    elif args.command == "shell":
        print_shell_functions()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
