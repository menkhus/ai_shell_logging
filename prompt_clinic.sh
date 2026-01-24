#!/bin/bash
# prompt_clinic.sh - Pre-process prompts before sending to Claude
#
# Analyzes prompts for directiveness, scope, and actionability.
# Uses local LLM (Ollama) to catch bad habits before they waste context.
#
# Usage:
#   prompt_clinic.sh "your prompt here"
#   echo "your prompt" | prompt_clinic.sh
#   prompt_clinic.sh -i  # interactive mode

set -e

# Configuration
MODEL="${PROMPT_CLINIC_MODEL:-mistral:7b-instruct}"
THRESHOLD="${PROMPT_CLINIC_THRESHOLD:-7}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
Usage: prompt_clinic.sh [OPTIONS] [PROMPT]

Analyze prompts before sending to Claude Code.

Options:
    -i, --interactive    Interactive mode (analyze multiple prompts)
    -s, --strict         Strict mode (threshold 8/10)
    -q, --quiet          Quiet mode (only show rewrite if needed)
    -m, --model MODEL    Ollama model to use (default: mistral:7b-instruct)
    -h, --help           Show this help

Environment:
    PROMPT_CLINIC_MODEL      Default model (default: mistral:7b-instruct)
    PROMPT_CLINIC_THRESHOLD  Minimum score to pass (default: 7)

Examples:
    prompt_clinic.sh "fix the bug in auth.py"
    echo "help me understand the codebase" | prompt_clinic.sh
    prompt_clinic.sh -i   # keeps prompting for input
EOF
    exit 0
}

check_ollama() {
    if ! command -v ollama &> /dev/null; then
        echo -e "${RED}Error: ollama not found${NC}" >&2
        echo "Install from: https://ollama.ai" >&2
        exit 1
    fi

    # Check if model is available
    if ! ollama list 2>/dev/null | grep -q "${MODEL%%:*}"; then
        echo -e "${YELLOW}Warning: Model '$MODEL' may not be installed${NC}" >&2
        echo "Run: ollama pull $MODEL" >&2
    fi
}

analyze_prompt() {
    local prompt="$1"
    local quiet="$2"

    [[ -z "$prompt" ]] && return

    # Detect obvious red flags locally first (fast path)
    local red_flags=""

    if [[ "$prompt" =~ "I wonder" ]] || [[ "$prompt" =~ "I'm curious" ]]; then
        red_flags="RESEARCH_LEAK: Contains exploratory language"
    elif [[ "$prompt" =~ "and also" ]] || [[ "$prompt" =~ "and maybe" ]]; then
        red_flags="SCOPE_CREEP: Multiple tasks detected"
    elif [[ "$prompt" =~ "What do you think" ]] || [[ "$prompt" =~ "what's your opinion" ]]; then
        red_flags="INTROSPECTION: Opinion-seeking in work context"
    elif [[ "$prompt" =~ "Let's explore" ]] || [[ "$prompt" =~ "help me understand" ]]; then
        red_flags="UNBOUNDED: No clear outcome stated"
    fi

    if [[ -n "$red_flags" && "$quiet" != "true" ]]; then
        echo -e "${YELLOW}Quick scan: $red_flags${NC}"
        echo ""
    fi

    # Full analysis with local LLM
    local analysis
    analysis=$(ollama run "$MODEL" <<EOF 2>/dev/null || echo "ANALYSIS_FAILED")
You are a prompt quality analyzer for Claude Code (a coding AI assistant).

Analyze this prompt and score it 1-10 on these criteria:
1. DIRECTIVE: Does it state a clear, specific outcome? (not vague goals)
2. SCOPED: Is it limited to ONE task? (not multiple combined)
3. ACTIONABLE: Can Claude begin work immediately? (not research/exploration)

PROMPT TO ANALYZE:
"$prompt"

Respond in EXACTLY this format:
DIRECTIVE: X/10 - [one line reason]
SCOPED: X/10 - [one line reason]
ACTIONABLE: X/10 - [one line reason]
OVERALL: X/10
VERDICT: PASS or FAIL
ISSUES: [bullet points if any, or "None"]
REWRITE: [improved version if score < 8, or "Not needed"]
EOF
)

    if [[ "$analysis" == "ANALYSIS_FAILED" ]]; then
        echo -e "${RED}Failed to analyze (is Ollama running?)${NC}" >&2
        return 1
    fi

    # Extract overall score
    local score
    score=$(echo "$analysis" | grep -o "OVERALL: [0-9]*" | grep -o "[0-9]*" || echo "0")

    # Extract verdict
    local verdict
    verdict=$(echo "$analysis" | grep "VERDICT:" | head -1)

    if [[ "$quiet" == "true" ]]; then
        # Quiet mode: only show if failed
        if [[ "$score" -lt "$THRESHOLD" ]]; then
            echo -e "${RED}SCORE: $score/10 - Below threshold ($THRESHOLD)${NC}"
            echo "$analysis" | grep -A1 "REWRITE:"
        else
            echo -e "${GREEN}PASS ($score/10)${NC}"
        fi
    else
        # Full output
        echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${BLUE}PROMPT CLINIC ANALYSIS${NC}"
        echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
        echo ""
        echo -e "Input: ${YELLOW}\"$prompt\"${NC}"
        echo ""
        echo "$analysis"
        echo ""

        if [[ "$score" -ge "$THRESHOLD" ]]; then
            echo -e "${GREEN}✓ Ready to send (score: $score/10)${NC}"
        else
            echo -e "${RED}✗ Needs work (score: $score/10, threshold: $THRESHOLD)${NC}"
        fi
        echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    fi

    # Return exit code based on pass/fail
    [[ "$score" -ge "$THRESHOLD" ]]
}

interactive_mode() {
    echo -e "${BLUE}Prompt Clinic - Interactive Mode${NC}"
    echo "Enter prompts to analyze. Ctrl+D or 'quit' to exit."
    echo ""

    while true; do
        echo -n -e "${GREEN}prompt> ${NC}"
        read -r prompt || break

        [[ "$prompt" == "quit" ]] || [[ "$prompt" == "exit" ]] && break
        [[ -z "$prompt" ]] && continue

        echo ""
        analyze_prompt "$prompt" "false"
        echo ""
    done

    echo "Goodbye."
}

# Parse arguments
INTERACTIVE=false
QUIET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--interactive)
            INTERACTIVE=true
            shift
            ;;
        -s|--strict)
            THRESHOLD=8
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            PROMPT="$1"
            shift
            ;;
    esac
done

# Check dependencies
check_ollama

# Run appropriate mode
if [[ "$INTERACTIVE" == "true" ]]; then
    interactive_mode
elif [[ -n "$PROMPT" ]]; then
    analyze_prompt "$PROMPT" "$QUIET"
elif [[ ! -t 0 ]]; then
    # Read from stdin
    PROMPT=$(cat)
    analyze_prompt "$PROMPT" "$QUIET"
else
    echo "Error: No prompt provided" >&2
    echo "Usage: prompt_clinic.sh \"your prompt here\"" >&2
    echo "       prompt_clinic.sh -i  # interactive mode" >&2
    exit 1
fi
