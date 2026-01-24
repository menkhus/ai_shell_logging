# The Silent Bleed: Why Claude Doesn't Grumble

## The Problem Nobody Talks About

You're paying for context. Every token. Every meandering thought. Every "hmm, let me think about this" that leads nowhere. And Claude won't complain. It'll happily burn through your context window while you explore tangentially related curiosities.

**The numbers are damning:**

| What We Found | The Reality |
|---------------|-------------|
| 98% wasted thinking | Claude thinks extensively, then does nothing |
| 37% todo completion | You start tasks, then wander off |
| 1,239 redundant calls | Same tool, back-to-back, no batching |
| 33 sessions too deep | Context bloat with no compaction |
| 49% healthy sessions | Half your sessions are suboptimal |

Claude is too polite to say: *"You're wasting both our time."*

---

## The Core Insight: Separate Curiosity from Work

**The cardinal sin:** Mixing introspection with execution.

When you're in a work session and think "I wonder how X works..." you've just poisoned your context. That curiosity - valid as it may be - doesn't belong in your build session. It belongs in a research session.

### The Discipline

```
WORK SESSION          RESEARCH SESSION
─────────────         ────────────────
- Directive prompts   - Exploratory prompts
- Clear outcomes      - "I wonder..."
- Tool execution      - Reading, learning
- Build, test, ship   - No tool calls needed
```

**Rule:** If you catch yourself being curious mid-task, STOP. Stash your context. Open a new session. Satisfy your curiosity. Return with clarity.

---

## Feedback Sensors: What Should Trigger Warnings

The system should grumble. Here's when:

### 1. Wandering Detector
**Signal:** Thinking block > 500 chars with no following tool call
**Meaning:** Claude is ruminating without acting
**User prompt:** "You seem to be thinking without acting. What specific outcome do you need?"

### 2. Depth Monitor
**Signal:** Conversation depth > 100 messages
**Meaning:** Context is bloated, recall is degrading
**User prompt:** "Session is deep. Consider /compact or start fresh."

### 3. Redundancy Alert
**Signal:** Same tool called 3+ times consecutively
**Meaning:** Batching opportunity missed
**User prompt:** "Multiple sequential [Tool] calls detected. Can these be batched?"

### 4. Error Spiral Detector
**Signal:** Errors > successful turns in last 5 messages
**Meaning:** Flailing, not recovering
**User prompt:** "Error pattern detected. Pause. Read the errors. What's actually wrong?"

### 5. Stale Todo Tracker
**Signal:** Todo in_progress for > 5 minutes with no update
**Meaning:** Task abandoned or blocked
**User prompt:** "Task '[X]' has been in progress without updates. Status?"

---

## The Offline Prompt Clinic

Before your prompts reach Claude, they should pass through a local filter. Use a small local model (Ollama, llama.cpp) to pre-process your prompts.

### prompt_clinic.sh

```bash
#!/bin/bash
# Analyze and clean prompts before sending to Claude

PROMPT="$1"

# Send to local model for analysis
ollama run mistral:7b-instruct <<EOF
Analyze this prompt for a coding AI assistant. Score 1-10 on:
1. DIRECTIVE: Does it state a clear outcome?
2. SCOPED: Is it limited to one task?
3. ACTIONABLE: Can work begin immediately?

If score < 7, rewrite it to be directive, scoped, and actionable.

PROMPT:
$PROMPT

Respond with:
SCORE: X/10
ISSUES: (if any)
REWRITE: (if needed)
EOF
```

### What the Clinic Catches

| Bad Prompt | Problem | Rewrite |
|------------|---------|---------|
| "Can you help me understand how the auth system works and maybe fix that bug?" | Two tasks, vague | "Fix the 401 error in auth.py:45. The token refresh is failing." |
| "I'm thinking about refactoring this..." | Introspective, no outcome | "Refactor UserService to use dependency injection. Start with the constructor." |
| "What do you think about..." | Opinion-seeking in work context | REJECT - move to research session |
| "Let's explore the codebase" | Unbounded exploration | "Find all files that handle payment processing. List paths only." |

---

## Hair-On-Fire Mode: How to Work

When you sit down with Claude, pretend:
- You're being billed by the second
- Your context window is 10x smaller than it is
- Every token must justify its existence

### The Protocol

1. **State the outcome first**
   - Bad: "I need to work on the login page"
   - Good: "Add 'Forgot Password' link to login.tsx, linking to /reset-password"

2. **One task per prompt**
   - Bad: "Fix the bug and add tests and update the docs"
   - Good: "Fix the null pointer in user.py:23" (then next prompt for tests)

3. **Provide constraints**
   - Bad: "Make it better"
   - Good: "Reduce response time to <200ms without changing the API contract"

4. **Name files explicitly**
   - Bad: "In that component we discussed"
   - Good: "In src/components/UserProfile.tsx"

5. **Stop Claude from exploring**
   - Bad: Let Claude read 15 files "for context"
   - Good: "Only read auth.py. Do not explore other files."

---

## The Curiosity Protocol

Curiosity is good. Undisciplined curiosity is expensive.

### When Curiosity Strikes Mid-Task

```
1. NOTICE: "I wonder how X works..."
2. CAPTURE: Write it down (todo, note, whatever)
3. CONTINUE: Finish current task
4. SEPARATE: Open new session for research
5. RETURN: Back to work with clean context
```

### Dedicated Research Sessions

Research sessions have different rules:
- No guilt about exploration
- No pressure for tool calls
- Read, ask, understand
- When satisfied, CLOSE the session
- Findings go into notes, not into work context

---

## Implementation: Three Tools to Build

### 1. `/focus` - Session Mode Enforcer

Sets the session to work-mode with guardrails:
- Enables depth monitoring
- Enables redundancy alerts
- Rejects exploratory prompts with redirect to research session
- Auto-suggests /compact at depth > 80

### 2. `/research` - Curiosity Sandbox

Opens a dedicated exploration session:
- No tool execution pressure
- No todo tracking
- Findings captured to a scratchpad
- Clean exit with summary

### 3. `/clinic` - Prompt Pre-Processor

Runs prompts through local AI before submission:
- Scores directiveness
- Catches scope creep
- Suggests rewrites
- Blocks introspective prompts in work sessions

---

## The Payoff

If you adopt this discipline:

| Metric | Current | Target |
|--------|---------|--------|
| Wasted thinking | 98% | <20% |
| Todo completion | 37% | >80% |
| Redundant calls | 1,239 | <100 |
| Session health | 49% | >85% |

More importantly: **You'll ship faster.** Not because Claude is faster, but because you stopped making it wander.

---

## The Uncomfortable Truth

The tool isn't the problem. The prompts are.

Claude will follow you anywhere - into productive work or into endless tangents. It doesn't distinguish. It doesn't judge. It doesn't grumble.

That's your job now.

Be directive. Be scoped. Be relentless about separating exploration from execution.

Your context window will thank you.

---

## Quick Reference Card

```
BEFORE PROMPTING, ASK:
[ ] Is this ONE task?
[ ] Is the outcome STATED?
[ ] Can work begin IMMEDIATELY?
[ ] Is this WORK or RESEARCH?

IF RESEARCH:
[ ] Open separate session
[ ] No guilt, no pressure
[ ] Capture findings
[ ] Return clean

WATCH FOR:
- "I wonder..." (research leak)
- "Can you also..." (scope creep)
- "What do you think..." (introspection)
- "Let's explore..." (unbounded)

WHEN STUCK:
- Read the error (really read it)
- State what you expected
- State what happened
- One fix attempt per prompt
```
