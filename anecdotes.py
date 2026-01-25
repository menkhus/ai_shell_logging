#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
anecdotes.py - Capture and analyze qualitative observations from validation sprints

Documents "what felt different" between native and focused modes.

Usage:
    ./anecdotes.py add <record_id> --note "observation"   # Add note to record
    ./anecdotes.py reflect <sprint_id>                    # Guided reflection for sprint
    ./anecdotes.py summary                                # Generate qualitative summary
    ./anecdotes.py template                               # Show reflection template
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from capture_schema import ValidationRecord


SPRINT_DIR = Path.home() / "ai_shell_logs" / "validation" / "sprints"
RECORDS_DIR = Path.home() / "ai_shell_logs" / "validation" / "records"
ANECDOTES_DIR = Path.home() / "ai_shell_logs" / "validation" / "anecdotes"


@dataclass
class SprintReflection:
    """Qualitative reflection on a sprint experience."""
    sprint_id: str
    mode: str
    timestamp: str = ""

    # Overall feel
    overall_experience: str = ""  # positive, neutral, negative
    cognitive_load: str = ""      # low, medium, high
    flow_state: str = ""          # disrupted, moderate, achieved

    # Specific observations
    friction_points: List[str] = field(default_factory=list)
    smooth_moments: List[str] = field(default_factory=list)
    surprises: List[str] = field(default_factory=list)

    # Behavioral changes
    noticed_habits: List[str] = field(default_factory=list)
    changed_approach: List[str] = field(default_factory=list)

    # Effectiveness perception
    felt_productive: bool = False
    would_use_again: bool = False
    recommend_to_others: bool = False

    # Open-ended
    best_moment: str = ""
    worst_moment: str = ""
    key_insight: str = ""
    free_notes: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class PromptAnecdote:
    """Anecdote attached to a specific prompt."""
    record_id: str
    timestamp: str = ""

    # What happened
    what_i_was_trying_to_do: str = ""
    what_actually_happened: str = ""
    how_it_felt: str = ""  # frustrated, neutral, satisfied, delighted

    # Intervention response (for focused mode)
    saw_suggestion: bool = False
    followed_suggestion: bool = False
    suggestion_helpful: bool = False

    # Learning
    would_do_differently: str = ""
    insight_gained: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


REFLECTION_TEMPLATE = """
================================================================================
SPRINT REFLECTION TEMPLATE
================================================================================

Sprint ID: {sprint_id}
Mode: {mode}
Date: {date}

--------------------------------------------------------------------------------
PART 1: OVERALL EXPERIENCE
--------------------------------------------------------------------------------

How would you describe your overall experience?
[ ] Positive - Felt good, productive, in control
[ ] Neutral - Neither particularly good nor bad
[ ] Negative - Felt frustrated, confused, or inefficient

How was your cognitive load?
[ ] Low - Easy to think, not mentally taxing
[ ] Medium - Some effort required but manageable
[ ] High - Mentally exhausting, hard to focus

Did you achieve flow state?
[ ] Disrupted - Constantly interrupted or distracted
[ ] Moderate - Some periods of focus
[ ] Achieved - Extended periods of productive flow

--------------------------------------------------------------------------------
PART 2: SPECIFIC OBSERVATIONS
--------------------------------------------------------------------------------

What were the friction points? (moments that felt awkward or slow)
1.
2.
3.

What went smoothly? (moments that felt natural or efficient)
1.
2.
3.

What surprised you?
1.
2.

--------------------------------------------------------------------------------
PART 3: BEHAVIORAL CHANGES
--------------------------------------------------------------------------------

Did you notice any habits? (good or bad patterns in your prompting)
1.
2.

Did you change your approach during the sprint? How?
1.
2.

--------------------------------------------------------------------------------
PART 4: EFFECTIVENESS
--------------------------------------------------------------------------------

Did you feel productive? [ ] Yes  [ ] No
Would you use this mode again? [ ] Yes  [ ] No
Would you recommend it to others? [ ] Yes  [ ] No

--------------------------------------------------------------------------------
PART 5: KEY MOMENTS
--------------------------------------------------------------------------------

Best moment of the sprint:


Worst moment of the sprint:


Key insight or learning:


--------------------------------------------------------------------------------
PART 6: FREE NOTES
--------------------------------------------------------------------------------

Any other observations, thoughts, or ideas:


================================================================================
"""

PROMPT_ANECDOTE_TEMPLATE = """
================================================================================
PROMPT ANECDOTE
================================================================================

Record ID: {record_id}
Prompt: {prompt_text}

--------------------------------------------------------------------------------

What were you trying to do?


What actually happened?


How did it feel? [ ] Frustrated  [ ] Neutral  [ ] Satisfied  [ ] Delighted

{focused_section}

What would you do differently next time?


Any insight gained?


================================================================================
"""

FOCUSED_SECTION = """
--------------------------------------------------------------------------------
INTERVENTION RESPONSE (Focused Mode)
--------------------------------------------------------------------------------

Did you see a suggestion/score? [ ] Yes  [ ] No
Did you follow the suggestion? [ ] Yes  [ ] No
Was the suggestion helpful? [ ] Yes  [ ] No
"""


def ensure_dirs():
    """Ensure anecdote directories exist."""
    ANECDOTES_DIR.mkdir(parents=True, exist_ok=True)


def load_record(record_id: str) -> Optional[ValidationRecord]:
    """Load a validation record by ID."""
    record_file = RECORDS_DIR / f"{record_id}.json"
    if not record_file.exists():
        # Try partial match
        matches = list(RECORDS_DIR.glob(f"*{record_id}*.json"))
        if matches:
            record_file = matches[0]
        else:
            return None

    with open(record_file) as f:
        return ValidationRecord.from_dict(json.load(f))


def save_record(record: ValidationRecord):
    """Save a validation record."""
    record_file = RECORDS_DIR / f"{record.record_id}.json"
    with open(record_file, 'w') as f:
        json.dump(record.to_dict(), f, indent=2)


def load_sprint(sprint_id: str) -> Optional[dict]:
    """Load sprint metadata."""
    sprint_file = SPRINT_DIR / f"{sprint_id}.json"
    if not sprint_file.exists():
        matches = list(SPRINT_DIR.glob(f"*{sprint_id}*.json"))
        if matches:
            sprint_file = matches[0]
        else:
            return None

    with open(sprint_file) as f:
        return json.load(f)


def save_reflection(reflection: SprintReflection):
    """Save a sprint reflection."""
    ensure_dirs()
    filepath = ANECDOTES_DIR / f"reflection_{reflection.sprint_id}.json"
    with open(filepath, 'w') as f:
        json.dump(asdict(reflection), f, indent=2)
    return filepath


def load_reflection(sprint_id: str) -> Optional[SprintReflection]:
    """Load a sprint reflection."""
    filepath = ANECDOTES_DIR / f"reflection_{sprint_id}.json"
    if not filepath.exists():
        # Try partial match
        matches = list(ANECDOTES_DIR.glob(f"*{sprint_id}*.json"))
        if matches:
            filepath = matches[0]
        else:
            return None

    with open(filepath) as f:
        data = json.load(f)
    return SprintReflection(**data)


def load_all_reflections() -> List[SprintReflection]:
    """Load all sprint reflections."""
    reflections = []
    for filepath in ANECDOTES_DIR.glob("reflection_*.json"):
        with open(filepath) as f:
            data = json.load(f)
        reflections.append(SprintReflection(**data))
    return reflections


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_add_note(record_id: str, note: str, felt: str = None,
                productive: bool = None):
    """Add a note/anecdote to a record."""
    record = load_record(record_id)
    if not record:
        print(f"Error: Record not found: {record_id}")
        sys.exit(1)

    # Update record
    if note:
        existing = record.user_notes or ""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_note = f"[{timestamp}] {note}"
        record.user_notes = f"{existing}\n{new_note}".strip()

    if productive is not None:
        record.felt_productive = productive

    save_record(record)
    print(f"Updated record: {record.record_id}")
    print(f"  Notes: {record.user_notes[:100]}...")


def cmd_reflect(sprint_id: str, interactive: bool = True):
    """Guided reflection for a sprint."""
    sprint = load_sprint(sprint_id)
    if not sprint:
        print(f"Error: Sprint not found: {sprint_id}")
        sys.exit(1)

    if interactive:
        print(f"\nReflecting on sprint: {sprint['sprint_id']}")
        print(f"Mode: {sprint['mode']}")
        print(f"Prompts: {len(sprint.get('records', []))}")
        print()

        reflection = SprintReflection(
            sprint_id=sprint['sprint_id'],
            mode=sprint['mode']
        )

        # Overall experience
        print("=" * 60)
        print("OVERALL EXPERIENCE")
        print("=" * 60)

        exp = input("\nOverall experience? [p]ositive / [n]eutral / [g]ative: ").lower()
        if exp.startswith('p'):
            reflection.overall_experience = "positive"
        elif exp.startswith('n'):
            reflection.overall_experience = "neutral"
        else:
            reflection.overall_experience = "negative"

        load = input("Cognitive load? [l]ow / [m]edium / [h]igh: ").lower()
        if load.startswith('l'):
            reflection.cognitive_load = "low"
        elif load.startswith('m'):
            reflection.cognitive_load = "medium"
        else:
            reflection.cognitive_load = "high"

        flow = input("Flow state? [d]isrupted / [m]oderate / [a]chieved: ").lower()
        if flow.startswith('d'):
            reflection.flow_state = "disrupted"
        elif flow.startswith('a'):
            reflection.flow_state = "achieved"
        else:
            reflection.flow_state = "moderate"

        # Specific observations
        print("\n" + "=" * 60)
        print("SPECIFIC OBSERVATIONS")
        print("=" * 60)

        print("\nFriction points (enter blank to stop):")
        while True:
            point = input("  - ").strip()
            if not point:
                break
            reflection.friction_points.append(point)

        print("\nSmooth moments (enter blank to stop):")
        while True:
            moment = input("  + ").strip()
            if not moment:
                break
            reflection.smooth_moments.append(moment)

        print("\nSurprises (enter blank to stop):")
        while True:
            surprise = input("  ! ").strip()
            if not surprise:
                break
            reflection.surprises.append(surprise)

        # Behavioral changes
        print("\n" + "=" * 60)
        print("BEHAVIORAL CHANGES")
        print("=" * 60)

        print("\nHabits you noticed (enter blank to stop):")
        while True:
            habit = input("  > ").strip()
            if not habit:
                break
            reflection.noticed_habits.append(habit)

        print("\nApproach changes (enter blank to stop):")
        while True:
            change = input("  ~ ").strip()
            if not change:
                break
            reflection.changed_approach.append(change)

        # Effectiveness
        print("\n" + "=" * 60)
        print("EFFECTIVENESS")
        print("=" * 60)

        reflection.felt_productive = input("\nFelt productive? [y/n]: ").lower().startswith('y')
        reflection.would_use_again = input("Would use again? [y/n]: ").lower().startswith('y')
        reflection.recommend_to_others = input("Recommend to others? [y/n]: ").lower().startswith('y')

        # Key moments
        print("\n" + "=" * 60)
        print("KEY MOMENTS")
        print("=" * 60)

        reflection.best_moment = input("\nBest moment: ").strip()
        reflection.worst_moment = input("Worst moment: ").strip()
        reflection.key_insight = input("Key insight: ").strip()

        # Free notes
        print("\n" + "=" * 60)
        print("FREE NOTES")
        print("=" * 60)
        reflection.free_notes = input("\nAnything else? ").strip()

        # Save
        filepath = save_reflection(reflection)
        print(f"\nReflection saved: {filepath}")

        # Also update records with subjective data
        for record_id in sprint.get('records', []):
            record = load_record(record_id)
            if record:
                record.felt_productive = reflection.felt_productive
                record.would_use_again = reflection.would_use_again
                save_record(record)

    else:
        # Non-interactive: just show template
        print(REFLECTION_TEMPLATE.format(
            sprint_id=sprint['sprint_id'],
            mode=sprint['mode'],
            date=datetime.now().strftime("%Y-%m-%d")
        ))


def cmd_template(record_id: str = None):
    """Show templates for anecdote capture."""
    if record_id:
        record = load_record(record_id)
        if record:
            focused_section = FOCUSED_SECTION if record.mode == "focused" else ""
            print(PROMPT_ANECDOTE_TEMPLATE.format(
                record_id=record.record_id,
                prompt_text=record.prompt.prompt_text[:100] + "...",
                focused_section=focused_section
            ))
        else:
            print(f"Record not found: {record_id}")
    else:
        print(REFLECTION_TEMPLATE.format(
            sprint_id="<sprint_id>",
            mode="<mode>",
            date=datetime.now().strftime("%Y-%m-%d")
        ))


def cmd_summary():
    """Generate qualitative summary from all reflections."""
    reflections = load_all_reflections()

    if not reflections:
        print("No reflections found.")
        print("Run: ./anecdotes.py reflect <sprint_id>")
        return

    # Group by mode
    native = [r for r in reflections if r.mode == "native"]
    focused = [r for r in reflections if r.mode == "focused"]

    print("=" * 70)
    print("QUALITATIVE SUMMARY: WHAT FELT DIFFERENT")
    print("=" * 70)
    print(f"\nReflections analyzed: {len(reflections)}")
    print(f"  Native mode: {len(native)}")
    print(f"  Focused mode: {len(focused)}")

    # Overall experience comparison
    print("\n" + "-" * 70)
    print("OVERALL EXPERIENCE")
    print("-" * 70)

    for mode_name, mode_reflections in [("Native", native), ("Focused", focused)]:
        if not mode_reflections:
            continue

        print(f"\n{mode_name.upper()} MODE:")

        # Experience distribution
        experiences = [r.overall_experience for r in mode_reflections]
        print(f"  Experience: {', '.join(experiences) or 'Not recorded'}")

        # Cognitive load
        loads = [r.cognitive_load for r in mode_reflections]
        print(f"  Cognitive load: {', '.join(loads) or 'Not recorded'}")

        # Flow state
        flows = [r.flow_state for r in mode_reflections]
        print(f"  Flow state: {', '.join(flows) or 'Not recorded'}")

        # Effectiveness
        productive = sum(1 for r in mode_reflections if r.felt_productive)
        would_use = sum(1 for r in mode_reflections if r.would_use_again)
        recommend = sum(1 for r in mode_reflections if r.recommend_to_others)
        total = len(mode_reflections)

        print(f"  Felt productive: {productive}/{total}")
        print(f"  Would use again: {would_use}/{total}")
        print(f"  Would recommend: {recommend}/{total}")

    # Friction points comparison
    print("\n" + "-" * 70)
    print("FRICTION POINTS")
    print("-" * 70)

    for mode_name, mode_reflections in [("Native", native), ("Focused", focused)]:
        if not mode_reflections:
            continue

        print(f"\n{mode_name.upper()} MODE:")
        all_frictions = []
        for r in mode_reflections:
            all_frictions.extend(r.friction_points)

        if all_frictions:
            for i, friction in enumerate(all_frictions[:5], 1):
                print(f"  {i}. {friction}")
        else:
            print("  (none recorded)")

    # Smooth moments comparison
    print("\n" + "-" * 70)
    print("SMOOTH MOMENTS")
    print("-" * 70)

    for mode_name, mode_reflections in [("Native", native), ("Focused", focused)]:
        if not mode_reflections:
            continue

        print(f"\n{mode_name.upper()} MODE:")
        all_smooth = []
        for r in mode_reflections:
            all_smooth.extend(r.smooth_moments)

        if all_smooth:
            for i, smooth in enumerate(all_smooth[:5], 1):
                print(f"  {i}. {smooth}")
        else:
            print("  (none recorded)")

    # Key insights
    print("\n" + "-" * 70)
    print("KEY INSIGHTS")
    print("-" * 70)

    for mode_name, mode_reflections in [("Native", native), ("Focused", focused)]:
        if not mode_reflections:
            continue

        print(f"\n{mode_name.upper()} MODE:")
        insights = [r.key_insight for r in mode_reflections if r.key_insight]
        if insights:
            for insight in insights:
                print(f"  - {insight}")
        else:
            print("  (none recorded)")

    # Behavioral changes
    print("\n" + "-" * 70)
    print("BEHAVIORAL PATTERNS")
    print("-" * 70)

    all_habits = []
    all_changes = []
    for r in reflections:
        all_habits.extend(r.noticed_habits)
        all_changes.extend(r.changed_approach)

    if all_habits:
        print("\nNoticed habits:")
        for habit in all_habits:
            print(f"  - {habit}")

    if all_changes:
        print("\nApproach changes:")
        for change in all_changes:
            print(f"  - {change}")

    # Verdict
    print("\n" + "=" * 70)
    print("QUALITATIVE VERDICT")
    print("=" * 70)

    native_positive = sum(1 for r in native if r.overall_experience == "positive")
    focused_positive = sum(1 for r in focused if r.overall_experience == "positive")

    native_would_use = sum(1 for r in native if r.would_use_again)
    focused_would_use = sum(1 for r in focused if r.would_use_again)

    if focused and native:
        if focused_positive > native_positive and focused_would_use > native_would_use:
            print("\nFocused mode feels better and users would use it again.")
        elif native_positive > focused_positive and native_would_use > focused_would_use:
            print("\nNative mode feels better and users would use it again.")
        else:
            print("\nMixed feelings - no clear qualitative preference.")
    elif focused:
        if focused_positive > 0:
            print(f"\nFocused mode feels {focused[0].overall_experience}.")
    elif native:
        if native_positive > 0:
            print(f"\nNative mode feels {native[0].overall_experience}.")

    print()


def cmd_list_records():
    """List recent records for adding anecdotes."""
    records = []
    for record_file in sorted(RECORDS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
        with open(record_file) as f:
            data = json.load(f)
        records.append(data)

    print("Recent records:")
    print("-" * 70)
    for r in records:
        prompt = r.get("prompt", {})
        notes = "+" if r.get("user_notes") else " "
        print(f"[{notes}] {r['record_id'][:30]}  {prompt.get('prompt_text', '')[:40]}...")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Capture qualitative observations from validation sprints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./anecdotes.py add val_123 --note "This felt awkward"
  ./anecdotes.py reflect sprint_native_123
  ./anecdotes.py summary
  ./anecdotes.py template
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # add
    add_p = subparsers.add_parser("add", help="Add note to a record")
    add_p.add_argument("record_id", help="Record ID")
    add_p.add_argument("--note", "-n", required=True, help="Note to add")
    add_p.add_argument("--felt", choices=["frustrated", "neutral", "satisfied", "delighted"])
    add_p.add_argument("--productive", action="store_true")
    add_p.add_argument("--not-productive", action="store_true")

    # reflect
    reflect_p = subparsers.add_parser("reflect", help="Guided reflection for sprint")
    reflect_p.add_argument("sprint_id", help="Sprint ID")
    reflect_p.add_argument("--non-interactive", action="store_true")

    # template
    template_p = subparsers.add_parser("template", help="Show reflection template")
    template_p.add_argument("record_id", nargs="?", help="Optional record ID for prompt template")

    # summary
    subparsers.add_parser("summary", help="Generate qualitative summary")

    # list
    subparsers.add_parser("list", help="List recent records")

    args = parser.parse_args()

    if args.command == "add":
        productive = None
        if args.productive:
            productive = True
        elif args.not_productive:
            productive = False
        cmd_add_note(args.record_id, args.note, args.felt, productive)
    elif args.command == "reflect":
        cmd_reflect(args.sprint_id, not args.non_interactive)
    elif args.command == "template":
        cmd_template(args.record_id)
    elif args.command == "summary":
        cmd_summary()
    elif args.command == "list":
        cmd_list_records()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
