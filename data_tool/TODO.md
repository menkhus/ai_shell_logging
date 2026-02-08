# Data Extraction TODO

## Key Findings for Protective Layer Design

Based on the complete analysis (77 sessions), a **protective layer** should:

1. **De-escalate wandering** (98% of thinking leads nowhere)
   - Signal: thinking blocks > 500 chars with no following tool
   - Action: prompt user to clarify intent

2. **Suggest compaction** (33 sessions too deep)
   - Signal: depth > 100 messages
   - Action: recommend /compact or new session

3. **Batch tool calls** (1,239 redundant)
   - Signal: same tool 3+ times consecutively
   - Action: suggest batching

4. **Catch error spirals** (5 sessions > 100% error rate)
   - Signal: errors > turns in last 5 messages
   - Action: pause and review

5. **Track todo abandonment** (37% completion)
   - Signal: todos in_progress > 5 minutes
   - Action: prompt for status update

---

## Phase 4: User Behavior Intervention [PENDING]

### Vision Statement

> These are not simple tasks. They must be informed by the session findings.
>
> I want to collect curiosity ideas, preprocess prompts, stash curiosity for research
> with session ID, stash the prompt analysis outcomes with session ID. I want /focus
> to be strategic work analysis of this LLM - not using any out-of-Claude process.
>
> **I want to benefit the Claude community first.**
>
> This AI is the most transparent, and I want to say I could not have done this
> without the transparency and traceability built into Claude Code. Debugging users
> is hard. Self-reflection is hard. I am so thankful I had a coding partner as brave,
> transparent, and trusting as Claude.
>
> — Mark, 2026-01-24

### Core Insight

**Debugging users is hard. Self-reflection is hard.**

The session data proves it: 98% wasted thinking, 37% todo completion, wandering
without action. The system doesn't grumble. Users need feedback sensors and
discipline tools that work *within* Claude's ecosystem.

### 4.1 `/focus` - Strategic Work Mode [PENDING]

**Not just guardrails - strategic work analysis of THIS LLM.**

Must include:
- Depth monitoring with compaction prompts
- Redundancy detection with batching suggestions
- Wandering detector (thinking without action)
- Todo tracking with abandonment alerts
- **Reject exploratory prompts** - redirect to /research
- All state persisted with session ID for cross-session learning

Design constraint: **No external processes.** Everything happens within Claude.

### 4.2 `/research` - Curiosity Sandbox [PENDING]

**Stash the curiosity, twiddle, return with clean context.**

Must include:
- Capture curiosity items with session ID linkage
- No tool execution pressure
- Scratchpad for findings
- Clean exit with summary
- Findings persisted for later retrieval
- Can reference: "What was I curious about in session X?"

### 4.3 `/clinic` - Prompt Pre-Processor [PENDING]

**Preprocess prompts, stash outcomes with session ID.**

Must include:
- Score prompts: directive, scoped, actionable
- Detect: research leaks, scope creep, introspection in work context
- Suggest rewrites before submission
- **Persist analysis outcomes** with session ID
- Build corpus of prompt patterns for community learning
- Integration with prompt_clinic.sh for offline analysis

See also: `../prompt_clinic.sh`, `../EFFECTIVE_CLAUDE_USAGE.md`

---

## Why This Matters

The data tells a story: users wander, abandon tasks, mix curiosity with work.
Claude follows dutifully into productive work or endless tangents. It doesn't
distinguish. It doesn't judge. It doesn't grumble.

**That's the user's job now.**

These tools make self-reflection easier. They give users feedback sensors they
lack internally. They separate exploration from execution.

Built on 77 sessions of transparent forensic data. Only possible because Claude
Code logs everything. Traceability enables debugging. Debugging enables growth.

**For the Claude community.**
