#!/bin/bash
# analyze_with_ollama.sh - Analyze prompt patterns using local LLM
#
# Uses your local ollama instance to critique your prompting patterns
# and suggest improvements. Runs OFFLINE - saves to file for later review.
#
# Usage: ./analyze_with_ollama.sh [model]
# Default model: gpt-oss:20b
#
# Output saved to: ~/ai_shell_logs/analysis/

MODEL="${1:-gpt-oss:20b}"
SCRIPT_DIR="$(dirname "$0")"
OUTPUT_DIR="$HOME/ai_shell_logs/analysis"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/prompt_analysis_${TIMESTAMP}.md"
PROMPT_FILE="$OUTPUT_DIR/prompt_analysis_${TIMESTAMP}.prompt"

mkdir -p "$OUTPUT_DIR"

echo "========================================"
echo "OFFLINE PROMPT ANALYSIS"
echo "========================================"
echo "Model:   $MODEL"
echo "Output:  $OUTPUT_FILE"
echo ""

# Save the prompt for reference
python3 "$SCRIPT_DIR/session_forensics.py" --ollama > "$PROMPT_FILE"
echo "Prompt saved to: $PROMPT_FILE"

# Run analysis in background
echo ""
echo "Starting ollama analysis (this may take several minutes)..."
echo "You can close this terminal - output will be saved."
echo ""

{
    echo "# Prompt Analysis - $(date)"
    echo "## Model: $MODEL"
    echo ""
    echo "## Analysis"
    echo ""
    cat "$PROMPT_FILE" | ollama run "$MODEL"
    echo ""
    echo "---"
    echo "Generated: $(date)"
} > "$OUTPUT_FILE" 2>&1 &

PID=$!
echo "Running in background (PID: $PID)"
echo ""
echo "To monitor: tail -f $OUTPUT_FILE"
echo "To check if complete: ps -p $PID"
echo ""
echo "When done, review: cat $OUTPUT_FILE"
echo "========================================"
