#!/usr/bin/env python3
"""
ai_export.py - Convert script logs to clean text or structured JSON

Uses pyte terminal emulator to properly render the terminal output,
then extracts conversation structure.

Usage:
    ai_export.py <logfile>              # Output clean text
    ai_export.py <logfile> --json       # Output structured JSON
    ai_export.py <logfile> -o out.json  # Write to file
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pyte
except ImportError:
    print("Error: pyte library required. Install with: pip install pyte", file=sys.stderr)
    sys.exit(1)


def render_log(logfile: Path, cols: int = 120, rows: int = 50) -> str:
    """Use pyte to emulate terminal and render final output."""
    # pyte's HistoryScreen keeps scrollback
    screen = pyte.HistoryScreen(cols, rows, history=100000)
    stream = pyte.Stream(screen)

    with open(logfile, 'rb') as f:
        content = f.read()

    # Feed content to terminal emulator
    try:
        stream.feed(content.decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"Warning: Error during terminal emulation: {e}", file=sys.stderr)

    # Collect all lines from history and current screen
    lines = []

    # Get history (scrolled off top) - each line is a dict of column -> Char
    for hist_line in screen.history.top:
        if isinstance(hist_line, dict):
            line_chars = []
            for col in range(cols):
                char = hist_line.get(col)
                if char:
                    line_chars.append(char.data if hasattr(char, 'data') else str(char))
                else:
                    line_chars.append(' ')
            lines.append(''.join(line_chars).rstrip())
        else:
            lines.append('')

    # Get current screen content
    for row in range(rows):
        line_chars = []
        for col in range(cols):
            char = screen.buffer[row][col]
            line_chars.append(char.data if hasattr(char, 'data') else ' ')
        lines.append(''.join(line_chars).rstrip())

    # Clean up: remove excessive blank lines
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_conversation(text: str) -> dict:
    """Parse rendered text into conversation structure."""
    # Extract metadata from filename or content
    conversation = {
        "metadata": {
            "exported_at": datetime.now().isoformat(),
            "format_version": "1.0"
        },
        "messages": [],
        "raw_text": text
    }

    # Look for user prompts (lines starting with ❯ or >)
    # and AI responses (blocks of text after prompts)
    lines = text.split('\n')
    current_message = None
    current_lines = []

    for line in lines:
        # Detect user input prompt
        if line.strip().startswith('❯') or re.match(r'^>\s+\S', line):
            # Save previous message if exists
            if current_message and current_lines:
                current_message['content'] = '\n'.join(current_lines).strip()
                if current_message['content']:
                    conversation['messages'].append(current_message)

            # Start new user message
            prompt_text = re.sub(r'^[❯>]\s*', '', line.strip())
            current_message = {
                "role": "user",
                "content": prompt_text
            }
            current_lines = []

            # If there's content on the prompt line, it's a short message
            if prompt_text:
                current_message['content'] = prompt_text
                conversation['messages'].append(current_message)
                current_message = {"role": "assistant", "content": ""}
                current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last message
    if current_message and current_lines:
        current_message['content'] = '\n'.join(current_lines).strip()
        if current_message['content']:
            conversation['messages'].append(current_message)

    return conversation


def main():
    parser = argparse.ArgumentParser(
        description='Convert AI session logs to clean text or JSON'
    )
    parser.add_argument('logfile', type=Path, help='Path to the log file')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('-o', '--output', type=Path, help='Output file (default: stdout)')
    parser.add_argument('--cols', type=int, default=120, help='Terminal columns (default: 120)')
    parser.add_argument('--rows', type=int, default=50, help='Terminal rows (default: 50)')

    args = parser.parse_args()

    if not args.logfile.exists():
        print(f"Error: File not found: {args.logfile}", file=sys.stderr)
        sys.exit(1)

    # Render the log through terminal emulator
    rendered = render_log(args.logfile, args.cols, args.rows)

    if args.json:
        result = parse_conversation(rendered)
        result['metadata']['source_file'] = str(args.logfile)
        output = json.dumps(result, indent=2)
    else:
        output = rendered

    if args.output:
        args.output.write_text(output)
        print(f"Written to: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
