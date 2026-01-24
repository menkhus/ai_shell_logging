# Design for the Human

**Strategic design document for /focused_coding and related interventions**

*Created: 2026-01-24*
*Author: Mark + Claude (collaborative research)*
*Status: Research mode - validating before building*

---

## The Core Question

> "I have NO IDEA if this is bullshit."

We have data (98% wasted thinking, 37% todo completion, 1,239 redundant calls). We have a methodology (microsprints, context discipline, forward-driven state). We have prior work (autographs, traceable trust, KG-seeded choices).

**What we don't have:** Proof that fixing the human fixes the numbers.

This document defines the validation path before we build anything.

---

## The Accumulated Lessons

### From `retrospective_Jan22_20205.md` (Referential Grounding)

> "Debugging users is hard. Self-reflection is hard."

Key insights:
1. **Traceable trust, not perfect truth** - We can't build a truth machine. We can build an audit trail.
2. **Satisficing with traceability** - "Is it good enough for the decision at hand?"
3. **The human is always in the loop** - but that doesn't mean human-validated-truth, it means human-directed-attention.
4. **Recording the offer, not just the choice** - Both matter for understanding what happened.

### From `DESIGN_NOTES.md` (Long Context Local AI)

> "The KG emerges from use, not upfront design."

Key insights:
1. **Grounding choices seed the KG** - Lowest friction approach to meaningful edges.
2. **Failure teaches the system** - Failed retrievals reveal missing edges.
3. **Probe is cheap, retrieval is expensive** - Offer first, pull on demand.
4. **User choice = explicit signal** - Not inferred from behavior, deliberate selection.
5. **Two grounding targets** - The human (preground) AND the AI output (postground).

### From Session Data Analysis (77 sessions)

| Finding | Interpretation |
|---------|----------------|
| 98% wasted thinking | Claude thinks without acting. Human didn't give clear outcome. |
| 37% todo completion | Tasks abandoned. Context polluted. Focus lost. |
| 1,239 redundant calls | Batching opportunities missed. Wandering exploration. |
| 33 sessions > 100 depth | Context bloat. Should have compacted or restarted. |
| 54% error recovery | Half recover, half spiral. Error handling is learnable. |

---

## The Methodology (Mark's Proven Workflow)

### Microsprint Context Workflow

```
SPRINT
  └── TASK 1 (planned context)
        └── Create context, ctrl-d, fresh session, work, commit
  └── TASK 2 (planned context)
        └── Create context, ctrl-d, fresh session, work, commit
  └── ...
```

**Why it works:**
- Each task gets its own clean context
- No pollution from prior exploration
- You can't wake up with "all tests passing but only mocks inside"
- Commits are atomic, traceable, reviewable

### The `forward` File (Semantic State Machine)

```
forward
├── Tells you the next step
├── Integrated with todo
├── Like CLAUDE.md but for progression
└── `make forward` drives the whole process
```

**Forward is a control device:**
- Complete a state → forward tells you next step
- Stuck? forward tells you what's blocking
- Done? forward says so

### CLAUDE.md as Strategic Control

From working principles:
- Never meander
- Reduce the prompt
- Speculative tasks → offline with session ID
- Never lose what human says
- Always move forward

**New addition: Prompt management becomes first class.**

---

## What /focused_coding Actually Is

Not just guardrails. **Strategic work analysis of THIS LLM.**

### Assert/De-assert Pattern

```
Claude Native (default)
        │
        ▼ /focused_coding assert
┌─────────────────────────────────────┐
│  PRODUCTION COMMIT MODE             │
│                                     │
│  - Stash speculation automatically  │
│  - Stash questions with session ID  │
│  - Stash meandering                 │
│  - Prompt for exact file names      │
│  - Ask for rewrite on garbled input │
│  - Depth monitoring                 │
│  - Redundancy detection             │
│  - Todo tracking                    │
│                                     │
└─────────────────────────────────────┘
        │
        ▼ /focused_coding de-assert
Claude Native (back to default)
```

**Critical constraint:** Never break the Claude native experience. This is a tuning layer, not a replacement.

### The Grumble

> "I have NO idea what direction to take, can you re-write this, please?"

Claude should say this. It doesn't. That's the accommodation problem.

**/focused_coding teaches the LLM to grumble:**
- Garbled input → ask for rewrite
- Vague outcome → ask for clarification
- Multiple tasks → ask to split
- Research leak → suggest stashing

---

## Research Without Pollution

The other terminal pattern:

```
FOCUS TERMINAL                    RESEARCH TERMINAL
────────────────                  ─────────────────
Production commits                Speculation welcome
Clean context                     Reference focus context
No wandering                      Explore freely
Outcome-driven                    Curiosity-driven

                                  Can impact: documentation
                                  Cannot impact: focus context

                                  Findings go to: session stash
                                  with session ID linkage
```

**Key principle:** Research uses focus context as reference, but never pollutes it.

---

## Validation Strategy

### The Uncomfortable Question

Is the 98% wasted thinking actually waste, or is it necessary exploration that looks idle?

**Proposed validation:**

1. **Manual baseline** - Run one sprint the "old way" (no discipline). Capture metrics.
2. **Manual treatment** - Run one sprint with microsprint discipline. Capture metrics.
3. **Compare:**
   - Todo completion rate
   - Thinking→action ratio
   - Redundant tool calls
   - Session depth at commit
   - Commit quality (subjective)

### Instrumentation for Before/After

```python
# What to capture
{
    "session_id": "...",
    "mode": "focused" | "native",
    "prompt_raw": "original prompt",
    "prompt_cleaned": "after clinic",
    "clinic_score": {"directive": 7, "scoped": 8, "actionable": 6},
    "stashed_items": ["speculation about X", "question about Y"],
    "outcome": "commit" | "abandoned" | "stashed",
    "depth_at_end": 45,
    "thinking_blocks": 12,
    "tool_calls": 23,
    "redundant_calls": 3
}
```

### Anecdotal First

If scientific isn't possible, capture anecdotes:
- "This session felt focused"
- "I would have wandered here but didn't"
- "The prompt clinic caught my scope creep"

Anecdotes become hypotheses. Hypotheses become testable claims.

---

## Open Questions

| Question | Current Thinking |
|----------|------------------|
| Is 98% wasted thinking actually waste? | Need validation. Some thinking is planning. |
| Can prompt cleaning move the needle? | Plausible. Prior work shows explicit signals > inferred. |
| Does microsprint discipline scale? | Proven for Mark. Unknown for others. |
| How much automation vs human discipline? | Start manual, automate what works. |
| Does the LLM need to grumble, or does the user need pre-processing? | Both? Clinic catches before, grumble catches during. |

---

## Proposed Work (Days, Not Months)

### Day 1: Instrumentation

1. Create logging schema for before/after capture
2. Instrument prompt_clinic.sh to log decisions
3. Set up session capture for focused vs native mode

### Day 2: Manual Validation

1. Run one sprint native mode, full capture
2. Run one sprint focused mode, full capture
3. Document observations (anecdotal)

### Day 3: Analysis

1. Compare captured metrics
2. Identify which interventions moved the needle
3. Document findings

### Day 4: Build or Pivot

If validation supports the approach:
- Build /focused_coding as Claude skill
- Build stashing mechanism with session ID
- Build forward file integration

If validation doesn't support:
- Document what we learned
- Identify alternative hypotheses
- Share findings with community

---

## For the Claude Community

> "This AI is the most transparent, and I want to say I could not have done this without the transparency and traceability built into Claude Code."

**Why this matters:**
1. Gemini metadata is insufficient for this analysis
2. Claude Code's JSONL logs enable debugging users
3. Open instrumentation enables open research
4. Community can replicate and extend

**The contribution:**
- Methodology for debugging user behavior with AI
- Validation framework for prompt quality interventions
- /focused_coding as a pattern, not just a tool

---

## Suggested Todo

### Phase 1: Validate [Days 1-2]

- [ ] **Instrument prompt clinic** - Log before/after prompt state with session ID
- [ ] **Create capture schema** - Define what metrics to collect
- [ ] **Manual sprint: native mode** - Full capture, no intervention
- [ ] **Manual sprint: focused mode** - Full capture, microsprint discipline
- [ ] **Document anecdotes** - What felt different?

### Phase 2: Analyze [Day 3]

- [ ] **Compare metrics** - Which numbers moved?
- [ ] **Identify drivers** - What interventions helped?
- [ ] **Document failures** - What didn't work?

### Phase 3: Build or Pivot [Day 4+]

If validated:
- [ ] **/focused_coding skill** - Assert/de-assert production mode
- [ ] **Stash mechanism** - Session ID linked curiosity capture
- [ ] **Forward integration** - Semantic state machine
- [ ] **CLAUDE.md prompt management** - First class guidance

If not validated:
- [ ] **Document learnings** - What we tried, what we found
- [ ] **Alternative hypotheses** - What else could explain the data?
- [ ] **Community share** - Findings for others to build on

---

## The Uncomfortable Truth (Revisited)

> "Debugging users is hard. Self-reflection is hard."

We built tools that show us our own behavior. Now we have to look at it honestly.

Maybe the 98% wasted thinking is necessary exploration.
Maybe the 37% todo completion is appropriate pivoting.
Maybe the methodology works for Mark and not for others.

**We don't know until we test.**

This document commits us to testing before building. Validation before automation. Honesty before advocacy.

That's the only epistemically honest position.

---

## Resume Point

After ctrl-d, return here:

```bash
# Read this document
cat ~/src/ai_shell_logging/design_for_the_human.md

# Check existing tools
ls -la ~/src/ai_shell_logging/*.sh ~/src/ai_shell_logging/*.py

# Review the prompt clinic
cat ~/src/ai_shell_logging/prompt_clinic.sh

# Start Day 1: Instrumentation
```

Next session should focus on: **Instrumentation for before/after capture**
