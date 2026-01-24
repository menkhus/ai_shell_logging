#!/usr/bin/env python3
"""
capture_schema.py - Schema for capturing before/after prompt state during validation sprints

This schema supports the validation framework for comparing:
- Native mode: Full capture, no intervention
- Focused mode: Full capture, microsprint discipline with prompt clinic

Usage:
    from capture_schema import PromptCapture, SessionOutcome, ValidationRecord

    # Capture a prompt before sending
    capture = PromptCapture(
        prompt_text="fix the bug in auth.py",
        mode="native",
        session_id="abc123"
    )
    capture.analyze()

    # After session, link to outcome
    outcome = SessionOutcome.from_session("abc123")
    record = ValidationRecord(prompt=capture, outcome=outcome)
    record.save()
"""

import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


# =============================================================================
# PROMPT-LEVEL CAPTURE
# =============================================================================

@dataclass
class PromptScores:
    """Scores from prompt clinic analysis."""
    directive: int = 0      # 1-10: Does it state a clear, specific outcome?
    scoped: int = 0         # 1-10: Is it limited to ONE task?
    actionable: int = 0     # 1-10: Can Claude begin work immediately?
    overall: int = 0        # 1-10: Combined score
    threshold: int = 7      # Passing threshold

    @property
    def passed(self) -> bool:
        return self.overall >= self.threshold


@dataclass
class PromptFlags:
    """Red flags detected in prompt."""
    research_leak: bool = False      # Contains exploratory language ("I wonder", "I'm curious")
    scope_creep: bool = False        # Multiple tasks detected ("and also", "and maybe")
    introspection: bool = False      # Opinion-seeking ("What do you think")
    unbounded: bool = False          # No clear outcome ("Let's explore", "help me understand")

    @property
    def any_flags(self) -> bool:
        return any([self.research_leak, self.scope_creep, self.introspection, self.unbounded])

    def to_list(self) -> List[str]:
        flags = []
        if self.research_leak:
            flags.append("RESEARCH_LEAK")
        if self.scope_creep:
            flags.append("SCOPE_CREEP")
        if self.introspection:
            flags.append("INTROSPECTION")
        if self.unbounded:
            flags.append("UNBOUNDED")
        return flags


@dataclass
class PromptClassification:
    """Classification from session_forensics style analysis."""
    # Type classification
    type: str = "unknown"  # debugging, implementation, refactoring, explanation, speculation, exploration, git_ops

    # Specificity
    specificity: str = "unknown"  # terse, brief, moderate, detailed

    # Tool fitness suggestion
    fitness: str = "unknown"  # claude_code, gemini_or_chat, either

    # Characteristics
    length: int = 0
    word_count: int = 0
    has_question: bool = False
    has_code: bool = False
    has_file_ref: bool = False


@dataclass
class PromptCapture:
    """Complete capture of a prompt's before/after state."""

    # Identity
    capture_id: str = ""
    timestamp: str = ""
    session_id: str = ""
    mode: str = "native"  # native | focused

    # Raw prompt
    prompt_text: str = ""

    # Scores (from prompt_clinic.sh or equivalent)
    scores: PromptScores = field(default_factory=PromptScores)

    # Flags (quick scan detection)
    flags: PromptFlags = field(default_factory=PromptFlags)

    # Classification (session_forensics style)
    classification: PromptClassification = field(default_factory=PromptClassification)

    # Rewrite (if suggested)
    rewrite_suggested: bool = False
    rewrite_text: str = ""
    rewrite_used: bool = False  # Did user accept the rewrite?

    # User decision
    sent_as_is: bool = True
    modified_before_send: bool = False
    final_prompt_text: str = ""  # What was actually sent

    def __post_init__(self):
        if not self.capture_id:
            self.capture_id = f"cap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self) % 10000:04d}"
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.final_prompt_text:
            self.final_prompt_text = self.prompt_text

    def analyze(self, use_heuristic_scores: bool = True):
        """Run all analyses on the prompt."""
        self._detect_flags()
        self._classify()
        if use_heuristic_scores:
            self._score_heuristic()

    def _detect_flags(self):
        """Quick scan for red flags (matches prompt_clinic.sh logic)."""
        text = self.prompt_text.lower()

        self.flags.research_leak = any(phrase in text for phrase in [
            "i wonder", "i'm curious", "curious about"
        ])
        self.flags.scope_creep = any(phrase in text for phrase in [
            "and also", "and maybe", "while you're at it", "plus also"
        ])
        self.flags.introspection = any(phrase in text for phrase in [
            "what do you think", "what's your opinion", "do you think"
        ])
        self.flags.unbounded = any(phrase in text for phrase in [
            "let's explore", "help me understand", "walk me through", "explain everything"
        ])

    def _score_heuristic(self):
        """
        Score prompt using heuristics (no LLM required).
        Provides reasonable estimates for directive/scoped/actionable.
        """
        text = self.prompt_text
        text_lower = text.lower()
        words = text.split()
        word_count = len(words)

        # DIRECTIVE: Does it state a clear, specific outcome?
        directive = 5  # Start neutral

        # Positive signals for directive
        if any(w in text_lower for w in ["fix", "add", "create", "implement", "remove", "update", "change"]):
            directive += 2  # Action verb
        if self.classification.has_file_ref:
            directive += 2  # Specific file reference
        if any(w in text_lower for w in ["in", "to", "for", "the"]):
            directive += 1  # Prepositions suggest specificity

        # Negative signals for directive
        if self.flags.unbounded:
            directive -= 3
        if self.flags.research_leak:
            directive -= 2
        if "?" in text and word_count < 10:
            directive -= 1  # Short questions are often vague
        if any(w in text_lower for w in ["maybe", "perhaps", "possibly", "might"]):
            directive -= 2

        # SCOPED: Is it limited to ONE task?
        scoped = 7  # Start optimistic

        # Negative signals for scoped
        if self.flags.scope_creep:
            scoped -= 4
        if text.count(" and ") > 1:
            scoped -= 2  # Multiple "and"s suggest multiple tasks
        if any(w in text_lower for w in ["also", "plus", "additionally", "as well"]):
            scoped -= 2
        if word_count > 100:
            scoped -= 2  # Very long prompts often have multiple asks

        # ACTIONABLE: Can Claude begin work immediately?
        actionable = 5  # Start neutral

        # Positive signals for actionable
        if self.classification.type in ["debugging", "implementation", "refactoring", "git_ops"]:
            actionable += 3  # Work-oriented task types
        if self.classification.has_file_ref:
            actionable += 2  # Has specific target
        if self.classification.has_code:
            actionable += 1  # Includes code context

        # Negative signals for actionable
        if self.classification.type in ["speculation", "explanation"]:
            actionable -= 2
        if self.flags.introspection:
            actionable -= 3
        if self.flags.research_leak:
            actionable -= 2
        if any(w in text_lower for w in ["research", "investigate", "explore", "understand"]):
            actionable -= 2

        # Clamp scores to 1-10
        self.scores.directive = max(1, min(10, directive))
        self.scores.scoped = max(1, min(10, scoped))
        self.scores.actionable = max(1, min(10, actionable))
        self.scores.overall = (self.scores.directive + self.scores.scoped + self.scores.actionable) // 3

        # Generate rewrite suggestion if score is low
        if self.scores.overall < self.scores.threshold:
            self._suggest_rewrite()

    def _suggest_rewrite(self):
        """Generate a rewrite suggestion based on detected issues."""
        suggestions = []

        if self.flags.research_leak:
            suggestions.append("Remove exploratory language ('I wonder', 'curious')")
        if self.flags.scope_creep:
            suggestions.append("Focus on ONE task - split into separate prompts")
        if self.flags.introspection:
            suggestions.append("State what you want done, not what you want to discuss")
        if self.flags.unbounded:
            suggestions.append("Add a specific outcome or deliverable")
        if self.scores.directive < 5:
            suggestions.append("Add an action verb and specific target")
        if not self.classification.has_file_ref and self.classification.type in ["debugging", "implementation"]:
            suggestions.append("Reference the specific file(s) to modify")

        if suggestions:
            self.rewrite_suggested = True
            self.rewrite_text = "Suggestions: " + "; ".join(suggestions)

    def _classify(self):
        """Classify prompt (matches session_forensics.py logic)."""
        text = self.prompt_text
        text_lower = text.lower()

        # Length metrics
        self.classification.length = len(text)
        self.classification.word_count = len(text.split())
        self.classification.has_question = "?" in text
        self.classification.has_code = bool(re.search(r'```|def |class |function |const |let |var ', text))
        self.classification.has_file_ref = bool(re.search(r'\.[a-z]{2,4}\b|/[a-z]', text_lower))

        # Type classification
        if any(w in text_lower for w in ["fix", "bug", "error", "broken", "doesn't work", "failed"]):
            self.classification.type = "debugging"
        elif any(w in text_lower for w in ["add", "create", "implement", "build", "write"]):
            self.classification.type = "implementation"
        elif any(w in text_lower for w in ["refactor", "clean", "improve", "optimize"]):
            self.classification.type = "refactoring"
        elif any(w in text_lower for w in ["explain", "what is", "how does", "why", "understand"]):
            self.classification.type = "explanation"
        elif any(w in text_lower for w in ["think", "consider", "idea", "maybe", "could we", "what if"]):
            self.classification.type = "speculation"
        elif any(w in text_lower for w in ["look at", "check", "find", "search", "where"]):
            self.classification.type = "exploration"
        elif any(w in text_lower for w in ["commit", "push", "pr", "merge", "branch"]):
            self.classification.type = "git_ops"

        # Specificity classification
        if self.classification.word_count < 5:
            self.classification.specificity = "terse"
        elif self.classification.word_count < 20:
            self.classification.specificity = "brief"
        elif self.classification.word_count < 50:
            self.classification.specificity = "moderate"
        else:
            self.classification.specificity = "detailed"

        # Fitness suggestion
        if self.classification.type in ["debugging", "implementation", "refactoring", "git_ops"]:
            self.classification.fitness = "claude_code"
        elif self.classification.type in ["speculation", "explanation"]:
            self.classification.fitness = "gemini_or_chat"
        elif self.classification.type == "exploration":
            self.classification.fitness = "either"

    def run_prompt_clinic(self) -> bool:
        """
        Run prompt_clinic.sh and parse results.
        Returns True if prompt passed.
        """
        try:
            result = subprocess.run(
                ["./prompt_clinic.sh", self.prompt_text],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent),
                timeout=60
            )
            output = result.stdout

            # Parse scores from output
            for line in output.split('\n'):
                if line.startswith("DIRECTIVE:"):
                    match = re.search(r'(\d+)/10', line)
                    if match:
                        self.scores.directive = int(match.group(1))
                elif line.startswith("SCOPED:"):
                    match = re.search(r'(\d+)/10', line)
                    if match:
                        self.scores.scoped = int(match.group(1))
                elif line.startswith("ACTIONABLE:"):
                    match = re.search(r'(\d+)/10', line)
                    if match:
                        self.scores.actionable = int(match.group(1))
                elif line.startswith("OVERALL:"):
                    match = re.search(r'(\d+)/10', line)
                    if match:
                        self.scores.overall = int(match.group(1))
                elif line.startswith("REWRITE:") and "Not needed" not in line:
                    self.rewrite_suggested = True
                    # Extract rewrite text (everything after "REWRITE: ")
                    rewrite_start = output.find("REWRITE:") + 8
                    self.rewrite_text = output[rewrite_start:].strip().split('\n')[0]

            return self.scores.passed
        except Exception as e:
            print(f"Warning: prompt_clinic.sh failed: {e}")
            return True  # Fail open


# =============================================================================
# SESSION-LEVEL OUTCOME
# =============================================================================

@dataclass
class SessionOutcome:
    """Outcome metrics from a completed session, for correlation with prompt quality."""

    # Identity
    session_id: str = ""
    linked_capture_ids: List[str] = field(default_factory=list)

    # Basic counts
    turns: int = 0
    tool_calls: int = 0
    errors: int = 0

    # Token usage
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_read_tokens: int = 0

    # Conversation structure
    max_depth: int = 0
    branch_count: int = 0
    dead_end_count: int = 0

    # Efficiency metrics (computed)
    tokens_per_tool: float = 0.0
    cache_rate: float = 0.0
    time_per_tool_ms: float = 0.0

    # Thinking efficiency
    thinking_blocks: int = 0
    wasted_thinking: int = 0  # Thinking with no following action
    wasted_thinking_pct: float = 0.0

    # Todo tracking
    todos_created: int = 0
    todos_completed: int = 0
    todo_completion_rate: float = 0.0

    # Session health classification
    health: str = "unknown"  # healthy, warning, poor
    outcome: str = "unknown"  # productive, exploratory, struggling

    # Timing
    total_duration_ms: float = 0.0
    first_timestamp: str = ""
    last_timestamp: str = ""

    @classmethod
    def from_session(cls, session_id: str, extractor_data: dict = None) -> 'SessionOutcome':
        """
        Create outcome from enhanced_extractor.py data.

        Args:
            session_id: The session ID to look up
            extractor_data: Pre-loaded data from enhanced_extractor.py export
                           If None, will attempt to extract fresh
        """
        outcome = cls(session_id=session_id)

        if extractor_data and session_id in extractor_data.get('sessions', {}):
            session = extractor_data['sessions'][session_id]

            outcome.turns = session.get('turns', 0)
            outcome.tool_calls = session.get('tool_calls', 0)
            outcome.errors = session.get('errors', 0)
            outcome.total_input_tokens = session.get('total_input_tokens', 0)
            outcome.total_output_tokens = session.get('total_output_tokens', 0)
            outcome.cache_read_tokens = session.get('total_cache_read', 0)
            outcome.max_depth = session.get('max_conversation_depth', 0)
            outcome.branch_count = session.get('branch_count', 0)
            outcome.dead_end_count = session.get('dead_end_count', 0)
            outcome.thinking_blocks = session.get('thinking_blocks', 0)
            outcome.todos_created = session.get('todos_created', 0)
            outcome.todos_completed = session.get('todos_completed', 0)
            outcome.total_duration_ms = session.get('total_turn_duration_ms', 0)
            outcome.first_timestamp = session.get('first_timestamp', '')
            outcome.last_timestamp = session.get('last_timestamp', '')

            # Compute derived metrics
            outcome._compute_metrics()

        return outcome

    def _compute_metrics(self):
        """Compute derived efficiency metrics."""
        total_tokens = self.total_input_tokens + self.total_output_tokens

        # Tokens per tool
        if self.tool_calls > 0:
            self.tokens_per_tool = total_tokens / self.tool_calls
            self.time_per_tool_ms = self.total_duration_ms / self.tool_calls

        # Cache rate
        if self.total_input_tokens > 0:
            self.cache_rate = self.cache_read_tokens / self.total_input_tokens * 100

        # Todo completion
        if self.todos_created > 0:
            self.todo_completion_rate = self.todos_completed / self.todos_created * 100

        # Health classification
        if self.errors == 0 and self.dead_end_count == 0:
            self.health = "healthy"
        elif self.errors <= 2 and self.dead_end_count <= 1:
            self.health = "warning"
        else:
            self.health = "poor"

        # Outcome classification
        if self.errors > 5 or self.dead_end_count > 2:
            self.outcome = "struggling"
        elif self.branch_count > 5 or self.todo_completion_rate < 30:
            self.outcome = "exploratory"
        else:
            self.outcome = "productive"


# =============================================================================
# VALIDATION RECORD
# =============================================================================

@dataclass
class ValidationRecord:
    """
    Complete validation record linking prompt capture to session outcome.
    This is the primary unit for before/after comparison.
    """

    # Identity
    record_id: str = ""
    timestamp: str = ""

    # Mode being validated
    mode: str = "native"  # native | focused
    sprint_id: str = ""   # Groups records from same validation sprint

    # Prompt capture
    prompt: PromptCapture = field(default_factory=PromptCapture)

    # Session outcome (populated after session completes)
    outcome: Optional[SessionOutcome] = None

    # User annotations (filled in during/after sprint)
    user_notes: str = ""
    felt_productive: Optional[bool] = None  # Subjective assessment
    would_use_again: Optional[bool] = None

    def __post_init__(self):
        if not self.record_id:
            self.record_id = f"val_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self) % 10000:04d}"
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "sprint_id": self.sprint_id,
            "prompt": asdict(self.prompt),
            "outcome": asdict(self.outcome) if self.outcome else None,
            "user_notes": self.user_notes,
            "felt_productive": self.felt_productive,
            "would_use_again": self.would_use_again
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ValidationRecord':
        """Create from dictionary."""
        record = cls(
            record_id=data.get("record_id", ""),
            timestamp=data.get("timestamp", ""),
            mode=data.get("mode", "native"),
            sprint_id=data.get("sprint_id", ""),
            user_notes=data.get("user_notes", ""),
            felt_productive=data.get("felt_productive"),
            would_use_again=data.get("would_use_again")
        )

        if data.get("prompt"):
            p = data["prompt"]
            record.prompt = PromptCapture(
                capture_id=p.get("capture_id", ""),
                timestamp=p.get("timestamp", ""),
                session_id=p.get("session_id", ""),
                mode=p.get("mode", "native"),
                prompt_text=p.get("prompt_text", ""),
                rewrite_suggested=p.get("rewrite_suggested", False),
                rewrite_text=p.get("rewrite_text", ""),
                rewrite_used=p.get("rewrite_used", False),
                sent_as_is=p.get("sent_as_is", True),
                modified_before_send=p.get("modified_before_send", False),
                final_prompt_text=p.get("final_prompt_text", "")
            )
            if p.get("scores"):
                record.prompt.scores = PromptScores(**p["scores"])
            if p.get("flags"):
                record.prompt.flags = PromptFlags(**p["flags"])
            if p.get("classification"):
                record.prompt.classification = PromptClassification(**p["classification"])

        if data.get("outcome"):
            o = data["outcome"]
            record.outcome = SessionOutcome(**o)

        return record

    def save(self, directory: Path = None):
        """Save record to JSON file."""
        if directory is None:
            directory = Path.home() / "ai_shell_logs" / "validation"
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"{self.record_id}.json"
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath


# =============================================================================
# SPRINT AGGREGATION
# =============================================================================

@dataclass
class SprintSummary:
    """
    Aggregate metrics from a validation sprint for comparison.
    """

    sprint_id: str = ""
    mode: str = "native"
    start_time: str = ""
    end_time: str = ""

    # Prompt-level aggregates
    total_prompts: int = 0
    prompts_passed_clinic: int = 0
    prompts_with_flags: int = 0
    rewrites_suggested: int = 0
    rewrites_used: int = 0

    # Score averages
    avg_directive_score: float = 0.0
    avg_scoped_score: float = 0.0
    avg_actionable_score: float = 0.0
    avg_overall_score: float = 0.0

    # Type distribution
    type_distribution: Dict[str, int] = field(default_factory=dict)
    fitness_distribution: Dict[str, int] = field(default_factory=dict)

    # Outcome-level aggregates
    total_sessions: int = 0
    sessions_healthy: int = 0
    sessions_warning: int = 0
    sessions_poor: int = 0
    sessions_productive: int = 0
    sessions_exploratory: int = 0
    sessions_struggling: int = 0

    # Efficiency averages
    avg_tokens_per_tool: float = 0.0
    avg_cache_rate: float = 0.0
    avg_todo_completion: float = 0.0
    avg_wasted_thinking_pct: float = 0.0

    # Error metrics
    total_errors: int = 0
    total_dead_ends: int = 0

    # Subjective
    felt_productive_count: int = 0
    would_use_again_count: int = 0

    @classmethod
    def from_records(cls, records: List[ValidationRecord], sprint_id: str = "") -> 'SprintSummary':
        """Aggregate a list of validation records into a summary."""
        if not records:
            return cls(sprint_id=sprint_id)

        summary = cls(
            sprint_id=sprint_id or records[0].sprint_id,
            mode=records[0].mode,
            start_time=min(r.timestamp for r in records),
            end_time=max(r.timestamp for r in records),
            total_prompts=len(records)
        )

        # Prompt-level aggregation
        directive_scores = []
        scoped_scores = []
        actionable_scores = []
        overall_scores = []

        for record in records:
            prompt = record.prompt

            if prompt.scores.passed:
                summary.prompts_passed_clinic += 1
            if prompt.flags.any_flags:
                summary.prompts_with_flags += 1
            if prompt.rewrite_suggested:
                summary.rewrites_suggested += 1
            if prompt.rewrite_used:
                summary.rewrites_used += 1

            if prompt.scores.directive > 0:
                directive_scores.append(prompt.scores.directive)
            if prompt.scores.scoped > 0:
                scoped_scores.append(prompt.scores.scoped)
            if prompt.scores.actionable > 0:
                actionable_scores.append(prompt.scores.actionable)
            if prompt.scores.overall > 0:
                overall_scores.append(prompt.scores.overall)

            # Type distribution
            ptype = prompt.classification.type
            summary.type_distribution[ptype] = summary.type_distribution.get(ptype, 0) + 1

            # Fitness distribution
            fitness = prompt.classification.fitness
            summary.fitness_distribution[fitness] = summary.fitness_distribution.get(fitness, 0) + 1

        # Compute averages
        if directive_scores:
            summary.avg_directive_score = sum(directive_scores) / len(directive_scores)
        if scoped_scores:
            summary.avg_scoped_score = sum(scoped_scores) / len(scoped_scores)
        if actionable_scores:
            summary.avg_actionable_score = sum(actionable_scores) / len(actionable_scores)
        if overall_scores:
            summary.avg_overall_score = sum(overall_scores) / len(overall_scores)

        # Outcome-level aggregation
        outcomes_with_data = [r for r in records if r.outcome is not None]
        summary.total_sessions = len(outcomes_with_data)

        tokens_per_tool = []
        cache_rates = []
        todo_completions = []
        wasted_thinking = []

        for record in outcomes_with_data:
            outcome = record.outcome

            # Health
            if outcome.health == "healthy":
                summary.sessions_healthy += 1
            elif outcome.health == "warning":
                summary.sessions_warning += 1
            else:
                summary.sessions_poor += 1

            # Outcome
            if outcome.outcome == "productive":
                summary.sessions_productive += 1
            elif outcome.outcome == "exploratory":
                summary.sessions_exploratory += 1
            else:
                summary.sessions_struggling += 1

            # Efficiency
            if outcome.tokens_per_tool > 0:
                tokens_per_tool.append(outcome.tokens_per_tool)
            cache_rates.append(outcome.cache_rate)
            if outcome.todo_completion_rate > 0:
                todo_completions.append(outcome.todo_completion_rate)
            wasted_thinking.append(outcome.wasted_thinking_pct)

            # Errors
            summary.total_errors += outcome.errors
            summary.total_dead_ends += outcome.dead_end_count

            # Subjective
            if record.felt_productive:
                summary.felt_productive_count += 1
            if record.would_use_again:
                summary.would_use_again_count += 1

        # Compute outcome averages
        if tokens_per_tool:
            summary.avg_tokens_per_tool = sum(tokens_per_tool) / len(tokens_per_tool)
        if cache_rates:
            summary.avg_cache_rate = sum(cache_rates) / len(cache_rates)
        if todo_completions:
            summary.avg_todo_completion = sum(todo_completions) / len(todo_completions)
        if wasted_thinking:
            summary.avg_wasted_thinking_pct = sum(wasted_thinking) / len(wasted_thinking)

        return summary

    def compare(self, other: 'SprintSummary') -> dict:
        """
        Compare this sprint (self) against another (other).
        Returns a dict of metric deltas (positive = self is better).
        """
        return {
            "mode_self": self.mode,
            "mode_other": other.mode,

            # Prompt quality (higher is better)
            "delta_avg_overall_score": self.avg_overall_score - other.avg_overall_score,
            "delta_prompts_passed_pct": (
                (self.prompts_passed_clinic / self.total_prompts * 100 if self.total_prompts else 0) -
                (other.prompts_passed_clinic / other.total_prompts * 100 if other.total_prompts else 0)
            ),
            "delta_rewrites_used_pct": (
                (self.rewrites_used / self.rewrites_suggested * 100 if self.rewrites_suggested else 0) -
                (other.rewrites_used / other.rewrites_suggested * 100 if other.rewrites_suggested else 0)
            ),

            # Session health (higher is better)
            "delta_healthy_pct": (
                (self.sessions_healthy / self.total_sessions * 100 if self.total_sessions else 0) -
                (other.sessions_healthy / other.total_sessions * 100 if other.total_sessions else 0)
            ),
            "delta_productive_pct": (
                (self.sessions_productive / self.total_sessions * 100 if self.total_sessions else 0) -
                (other.sessions_productive / other.total_sessions * 100 if other.total_sessions else 0)
            ),

            # Efficiency (lower is better for tokens, higher for cache)
            "delta_tokens_per_tool": other.avg_tokens_per_tool - self.avg_tokens_per_tool,  # Inverted
            "delta_cache_rate": self.avg_cache_rate - other.avg_cache_rate,
            "delta_todo_completion": self.avg_todo_completion - other.avg_todo_completion,
            "delta_wasted_thinking": other.avg_wasted_thinking_pct - self.avg_wasted_thinking_pct,  # Inverted

            # Errors (lower is better)
            "delta_errors": other.total_errors - self.total_errors,  # Inverted
            "delta_dead_ends": other.total_dead_ends - self.total_dead_ends,  # Inverted

            # Subjective (higher is better)
            "delta_felt_productive_pct": (
                (self.felt_productive_count / self.total_sessions * 100 if self.total_sessions else 0) -
                (other.felt_productive_count / other.total_sessions * 100 if other.total_sessions else 0)
            )
        }


# =============================================================================
# JSON SCHEMA EXPORT
# =============================================================================

def export_json_schema() -> dict:
    """Export the capture schema as JSON Schema for documentation."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Validation Capture Schema",
        "description": "Schema for capturing before/after prompt state during validation sprints",
        "type": "object",
        "definitions": {
            "PromptScores": {
                "type": "object",
                "properties": {
                    "directive": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Does it state a clear, specific outcome?"},
                    "scoped": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Is it limited to ONE task?"},
                    "actionable": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Can Claude begin work immediately?"},
                    "overall": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Combined score"},
                    "threshold": {"type": "integer", "default": 7, "description": "Passing threshold"}
                }
            },
            "PromptFlags": {
                "type": "object",
                "properties": {
                    "research_leak": {"type": "boolean", "description": "Contains exploratory language"},
                    "scope_creep": {"type": "boolean", "description": "Multiple tasks detected"},
                    "introspection": {"type": "boolean", "description": "Opinion-seeking"},
                    "unbounded": {"type": "boolean", "description": "No clear outcome"}
                }
            },
            "PromptClassification": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["debugging", "implementation", "refactoring", "explanation", "speculation", "exploration", "git_ops", "unknown"]},
                    "specificity": {"type": "string", "enum": ["terse", "brief", "moderate", "detailed", "unknown"]},
                    "fitness": {"type": "string", "enum": ["claude_code", "gemini_or_chat", "either", "unknown"]},
                    "length": {"type": "integer"},
                    "word_count": {"type": "integer"},
                    "has_question": {"type": "boolean"},
                    "has_code": {"type": "boolean"},
                    "has_file_ref": {"type": "boolean"}
                }
            },
            "PromptCapture": {
                "type": "object",
                "properties": {
                    "capture_id": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "session_id": {"type": "string"},
                    "mode": {"type": "string", "enum": ["native", "focused"]},
                    "prompt_text": {"type": "string"},
                    "scores": {"$ref": "#/definitions/PromptScores"},
                    "flags": {"$ref": "#/definitions/PromptFlags"},
                    "classification": {"$ref": "#/definitions/PromptClassification"},
                    "rewrite_suggested": {"type": "boolean"},
                    "rewrite_text": {"type": "string"},
                    "rewrite_used": {"type": "boolean"},
                    "sent_as_is": {"type": "boolean"},
                    "modified_before_send": {"type": "boolean"},
                    "final_prompt_text": {"type": "string"}
                },
                "required": ["prompt_text", "mode"]
            },
            "SessionOutcome": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "turns": {"type": "integer"},
                    "tool_calls": {"type": "integer"},
                    "errors": {"type": "integer"},
                    "total_input_tokens": {"type": "integer"},
                    "total_output_tokens": {"type": "integer"},
                    "cache_read_tokens": {"type": "integer"},
                    "max_depth": {"type": "integer"},
                    "branch_count": {"type": "integer"},
                    "dead_end_count": {"type": "integer"},
                    "tokens_per_tool": {"type": "number"},
                    "cache_rate": {"type": "number"},
                    "thinking_blocks": {"type": "integer"},
                    "wasted_thinking": {"type": "integer"},
                    "wasted_thinking_pct": {"type": "number"},
                    "todos_created": {"type": "integer"},
                    "todos_completed": {"type": "integer"},
                    "todo_completion_rate": {"type": "number"},
                    "health": {"type": "string", "enum": ["healthy", "warning", "poor", "unknown"]},
                    "outcome": {"type": "string", "enum": ["productive", "exploratory", "struggling", "unknown"]},
                    "total_duration_ms": {"type": "number"}
                }
            },
            "ValidationRecord": {
                "type": "object",
                "properties": {
                    "record_id": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "mode": {"type": "string", "enum": ["native", "focused"]},
                    "sprint_id": {"type": "string"},
                    "prompt": {"$ref": "#/definitions/PromptCapture"},
                    "outcome": {"$ref": "#/definitions/SessionOutcome"},
                    "user_notes": {"type": "string"},
                    "felt_productive": {"type": "boolean"},
                    "would_use_again": {"type": "boolean"}
                },
                "required": ["mode", "prompt"]
            }
        },
        "properties": {
            "validation_record": {"$ref": "#/definitions/ValidationRecord"}
        }
    }


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Capture schema for validation sprints")
    parser.add_argument("--schema", action="store_true", help="Export JSON schema")
    parser.add_argument("--test", type=str, help="Test analysis on a prompt")
    args = parser.parse_args()

    if args.schema:
        schema = export_json_schema()
        print(json.dumps(schema, indent=2))
    elif args.test:
        capture = PromptCapture(
            prompt_text=args.test,
            mode="native",
            session_id="test_session"
        )
        capture.analyze()
        print(json.dumps(asdict(capture), indent=2))
    else:
        parser.print_help()
