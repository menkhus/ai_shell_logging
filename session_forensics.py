#!/usr/bin/env python3
"""
session_forensics.py - Analyze Claude Code usage patterns for self-improvement

Extracts patterns that reveal:
- Meandering (topic drift within sessions)
- Task fragmentation (many small unrelated tasks)
- Prompt quality (vague vs specific asks)
- Tool fitness (coding vs speculation vs research)

Can output prompts for analysis by local LLM (ollama).

Usage:
    session_forensics.py                     # Overview of all sessions
    session_forensics.py --prompts           # Extract user prompts for LLM analysis
    session_forensics.py --session <id>      # Deep dive on one session
    session_forensics.py --fitness           # Analyze task/tool fitness
    session_forensics.py --ollama            # Format for piping to ollama
"""

import json
import sys
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def find_sessions(claude_dir: Path = None) -> list:
    """Find all session files."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"

    sessions = []
    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            if jsonl.name == "sessions-index.json":
                continue
            stat = jsonl.stat()
            sessions.append({
                "path": jsonl,
                "project": project_dir.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime)
            })

    return sorted(sessions, key=lambda x: x["mtime"], reverse=True)


def extract_user_prompts(jsonl_path: Path) -> list:
    """Extract all user prompts from a session."""
    prompts = []

    with open(jsonl_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "user":
                continue

            msg = entry.get("message", {})
            content = msg.get("content", "")

            # Handle string content (direct prompt)
            if isinstance(content, str) and content.strip():
                prompts.append({
                    "text": content,
                    "timestamp": entry.get("timestamp"),
                    "type": "prompt"
                })
            # Handle list content (might have tool results mixed in)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        prompts.append({
                            "text": item,
                            "timestamp": entry.get("timestamp"),
                            "type": "prompt"
                        })

    return prompts


def classify_prompt(text: str) -> dict:
    """Classify a prompt by type and characteristics."""
    text_lower = text.lower()

    classification = {
        "length": len(text),
        "word_count": len(text.split()),
        "has_question": "?" in text,
        "has_code": bool(re.search(r'```|def |class |function |const |let |var ', text)),
        "has_file_ref": bool(re.search(r'\.[a-z]{2,4}\b|/[a-z]', text_lower)),
        "type": "unknown",
        "specificity": "unknown",
        "fitness": "unknown"  # claude vs gemini vs other
    }

    # Classify type
    if any(w in text_lower for w in ["fix", "bug", "error", "broken", "doesn't work", "failed"]):
        classification["type"] = "debugging"
    elif any(w in text_lower for w in ["add", "create", "implement", "build", "write"]):
        classification["type"] = "implementation"
    elif any(w in text_lower for w in ["refactor", "clean", "improve", "optimize"]):
        classification["type"] = "refactoring"
    elif any(w in text_lower for w in ["explain", "what is", "how does", "why", "understand"]):
        classification["type"] = "explanation"
    elif any(w in text_lower for w in ["think", "consider", "idea", "maybe", "could we", "what if"]):
        classification["type"] = "speculation"
    elif any(w in text_lower for w in ["look at", "check", "find", "search", "where"]):
        classification["type"] = "exploration"
    elif any(w in text_lower for w in ["commit", "push", "pr", "merge", "branch"]):
        classification["type"] = "git_ops"

    # Classify specificity
    if classification["word_count"] < 5:
        classification["specificity"] = "terse"
    elif classification["word_count"] < 20:
        classification["specificity"] = "brief"
    elif classification["word_count"] < 50:
        classification["specificity"] = "moderate"
    else:
        classification["specificity"] = "detailed"

    # Suggest tool fitness
    if classification["type"] in ["debugging", "implementation", "refactoring", "git_ops"]:
        classification["fitness"] = "claude_code"  # Hands-on coding
    elif classification["type"] in ["speculation", "explanation"]:
        classification["fitness"] = "gemini_or_chat"  # Conversation/ideation
    elif classification["type"] == "exploration":
        classification["fitness"] = "either"

    return classification


def analyze_session(jsonl_path: Path) -> dict:
    """Analyze a single session for patterns."""
    prompts = extract_user_prompts(jsonl_path)

    if not prompts:
        return {"prompt_count": 0}

    classifications = [classify_prompt(p["text"]) for p in prompts]

    # Aggregate
    type_counts = defaultdict(int)
    fitness_counts = defaultdict(int)
    specificity_counts = defaultdict(int)

    for c in classifications:
        type_counts[c["type"]] += 1
        fitness_counts[c["fitness"]] += 1
        specificity_counts[c["specificity"]] += 1

    # Detect meandering (topic changes)
    types_sequence = [c["type"] for c in classifications]
    topic_changes = sum(1 for i in range(1, len(types_sequence)) if types_sequence[i] != types_sequence[i-1])

    return {
        "prompt_count": len(prompts),
        "type_distribution": dict(type_counts),
        "fitness_distribution": dict(fitness_counts),
        "specificity_distribution": dict(specificity_counts),
        "topic_changes": topic_changes,
        "meandering_score": topic_changes / max(len(prompts) - 1, 1),
        "prompts": prompts,
        "classifications": classifications
    }


def print_overview(sessions: list):
    """Print overview of all sessions."""
    print("=" * 70)
    print("SESSION FORENSICS OVERVIEW")
    print("=" * 70)

    print(f"\nTotal sessions: {len(sessions)}")

    if sessions:
        oldest = min(s["mtime"] for s in sessions)
        newest = max(s["mtime"] for s in sessions)
        print(f"Date range: {oldest.date()} to {newest.date()}")
        print(f"Total size: {sum(s['size'] for s in sessions) / 1024 / 1024:.1f} MB")

    # Aggregate analysis
    all_types = defaultdict(int)
    all_fitness = defaultdict(int)
    total_prompts = 0
    total_meandering = 0

    print("\nAnalyzing sessions...")
    for session in sessions:
        try:
            analysis = analyze_session(session["path"])
            total_prompts += analysis.get("prompt_count", 0)
            total_meandering += analysis.get("meandering_score", 0)

            for t, c in analysis.get("type_distribution", {}).items():
                all_types[t] += c
            for f, c in analysis.get("fitness_distribution", {}).items():
                all_fitness[f] += c
        except Exception as e:
            pass

    print(f"\n📊 AGGREGATE PATTERNS ({total_prompts} total prompts)")

    print("\n  Prompt types:")
    for t, c in sorted(all_types.items(), key=lambda x: -x[1]):
        pct = 100 * c / total_prompts if total_prompts else 0
        print(f"    {t}: {c} ({pct:.1f}%)")

    print("\n  Tool fitness (suggested):")
    for f, c in sorted(all_fitness.items(), key=lambda x: -x[1]):
        pct = 100 * c / total_prompts if total_prompts else 0
        bar = "█" * int(pct / 5)
        print(f"    {f}: {c} ({pct:.1f}%) {bar}")

    avg_meandering = total_meandering / len(sessions) if sessions else 0
    print(f"\n  Average meandering score: {avg_meandering:.2f}")
    print("    (0 = focused, 1 = constant topic switching)")

    print("\n" + "=" * 70)


def export_prompts_for_llm(sessions: list, limit: int = 50):
    """Export prompts in a format suitable for LLM analysis."""
    all_prompts = []

    for session in sessions[:20]:  # Sample recent sessions
        try:
            analysis = analyze_session(session["path"])
            for i, p in enumerate(analysis.get("prompts", [])[:10]):
                c = analysis["classifications"][i]
                all_prompts.append({
                    "prompt": p["text"][:500],  # Truncate long prompts
                    "classified_type": c["type"],
                    "classified_fitness": c["fitness"],
                    "word_count": c["word_count"]
                })
        except:
            pass

    return all_prompts[:limit]


def format_for_ollama(prompts: list) -> str:
    """Format prompts for analysis by local ollama."""
    prompt_texts = "\n---\n".join([
        f"Prompt {i+1}: {p['prompt'][:300]}"
        for i, p in enumerate(prompts[:20])
    ])

    analysis_prompt = f"""Analyze these user prompts from coding sessions with an AI assistant.
For each, assess:
1. Clarity (1-5): Is the ask specific or vague?
2. Fitness: Is this suited for a coding assistant, or better for conversation/research?
3. Improvement: How could the prompt be more effective?

Prompts to analyze:
{prompt_texts}

Provide a summary of patterns you notice - meandering, lack of specificity,
mismatch between task type and tool, etc. Be direct and constructive."""

    return analysis_prompt


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze Claude Code usage patterns")
    parser.add_argument("--prompts", action="store_true", help="Export prompts for analysis")
    parser.add_argument("--session", type=str, help="Analyze specific session ID")
    parser.add_argument("--fitness", action="store_true", help="Focus on tool fitness analysis")
    parser.add_argument("--ollama", action="store_true", help="Format for ollama analysis")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    sessions = find_sessions()

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        sys.exit(1)

    if args.ollama:
        prompts = export_prompts_for_llm(sessions)
        print(format_for_ollama(prompts))
    elif args.prompts:
        prompts = export_prompts_for_llm(sessions)
        if args.json:
            print(json.dumps(prompts, indent=2))
        else:
            for p in prompts:
                print(f"[{p['classified_type']}] {p['prompt'][:100]}...")
    elif args.session:
        # Find matching session
        for s in sessions:
            if args.session in str(s["path"]):
                analysis = analyze_session(s["path"])
                if args.json:
                    print(json.dumps(analysis, indent=2, default=str))
                else:
                    print(f"Session: {s['path'].name}")
                    print(f"Prompts: {analysis['prompt_count']}")
                    print(f"Meandering: {analysis['meandering_score']:.2f}")
                    print(f"Types: {analysis['type_distribution']}")
                break
    else:
        print_overview(sessions)


if __name__ == "__main__":
    main()
