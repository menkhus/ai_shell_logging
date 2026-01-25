#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
ai_export.py - Convert script logs to clean text or structured JSON/JSONL

Uses pyte terminal emulator to properly render the terminal output,
then extracts conversation structure.

Usage:
    ai_export.py <logfile>              # Output clean text
    ai_export.py <logfile> --json       # Output legacy JSON format
    ai_export.py <logfile> --jsonl      # Output Claude-compatible JSONL
    ai_export.py <logfile> --jsonl --index  # JSONL + update session index
    ai_export.py <logfile> -o out.json  # Write to file
"""

import argparse
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

try:
    import pyte
except ImportError:
    print("Error: pyte library required. Install with: pip install pyte", file=sys.stderr)
    sys.exit(1)

# Import session converter and index (optional - graceful degradation)
try:
    from session_converter import SessionConverter, parse_timestamp_from_filename
    from session_index import SessionIndex
    HAS_SESSION_SUPPORT = True
except ImportError:
    HAS_SESSION_SUPPORT = False


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
    """Parse rendered text into conversation structure (legacy format)."""
    # Extract metadata from filename or content
    conversation = {
        "metadata": {
            "exported_at": datetime.now().isoformat(),
            "format_version": "1.0"
        },
        "messages": [],
        "raw_text": text
    }

    # Look for user prompts:
    #   - ❯ or > (shell prompts)
    #   - >>> (ollama/python REPL style)
    #   - gemini> (gemini CLI)
    # Also handle continuation lines:
    #   - ... (ollama wraps long input with this prefix)
    lines = text.split('\n')
    messages = []
    current_role = None
    current_content = []

    for line in lines:
        stripped = line.strip()

        # Detect user input prompt
        is_prompt = stripped.startswith('❯') or \
                    stripped.startswith('>>>') or \
                    stripped.startswith('gemini>') or \
                    re.match(r'^>\s+\S', line)

        # Detect continuation line (ollama wraps long prompts with ...)
        is_continuation = stripped.startswith('...')

        if is_prompt:
            # Save previous message if exists
            if current_role and current_content:
                content = '\n'.join(current_content).strip()
                if content:
                    messages.append({"role": current_role, "content": content})

            # Start new user message - strip prompt prefix
            prompt_text = re.sub(r'^(❯|>>>|gemini>|>)\s*', '', stripped)
            current_role = "user"
            current_content = [prompt_text] if prompt_text else []

        elif is_continuation and current_role == "user":
            # Continuation of user prompt - strip ... prefix and append
            cont_text = re.sub(r'^\.\.\.\s*', '', stripped)
            current_content.append(cont_text)

        elif current_role == "user" and current_content:
            # First non-continuation line after user prompt = start of assistant response
            # Save user message first
            content = ' '.join(current_content).strip()  # Join with space for wrapped lines
            if content:
                messages.append({"role": "user", "content": content})

            # Start assistant response
            current_role = "assistant"
            current_content = [line] if line.strip() else []

        else:
            # Continue current message (assistant response or initial content)
            if current_role is None and line.strip():
                # Content before first prompt - treat as assistant (preamble)
                current_role = "assistant"
            if current_role:
                current_content.append(line)

    # Don't forget the last message
    if current_role and current_content:
        if current_role == "user":
            content = ' '.join(current_content).strip()
        else:
            content = '\n'.join(current_content).strip()
        if content:
            messages.append({"role": current_role, "content": content})

    conversation['messages'] = messages
    return conversation


def parse_messages(text: str) -> list:
    """
    Parse rendered text into a list of message dicts.

    Returns list of {"role": "user"|"assistant", "content": "..."}
    """
    conv = parse_conversation(text)
    return conv.get("messages", [])


def convert_to_jsonl(logfile: Path, app: str = None, model: str = None,
                     tag: str = None, cwd: str = None, meta: dict = None) -> SessionConverter:
    """
    Convert log file to Claude-compatible JSONL format.

    Args:
        logfile: Path to the raw log file
        app: Application name (auto-detected from path if not provided)
        model: Model name (optional)
        tag: Session tag (optional)
        cwd: Working directory (optional)
        meta: Full metadata dict from .meta file (overrides other args)

    Returns:
        SessionConverter with messages loaded
    """
    if not HAS_SESSION_SUPPORT:
        raise ImportError("session_converter module required for JSONL output")

    # Use metadata if provided
    if meta:
        app = meta.get("app", app)
        tag = meta.get("tag", tag)
        cwd = meta.get("cwd", cwd)

    # Auto-detect app from path
    if app is None:
        # Path like ~/ai_shell_logs/ollama/2026-01-24_121414.log
        app = logfile.parent.name
        if app in ["raw", "sessions", "legacy"]:
            app = logfile.parent.parent.name

    # Parse timestamp from filename
    start_time = parse_timestamp_from_filename(logfile.name)

    # Render and parse log
    rendered = render_log(logfile)
    messages = parse_messages(rendered)

    # Create converter with enhanced metadata
    converter = SessionConverter(
        app=app,
        source_file=logfile,
        start_time=start_time,
        model=model,
        tag=tag,
        cwd=cwd,
        meta=meta  # Pass full metadata for enhanced fields
    )

    # Add messages
    for msg in messages:
        converter.add_message(msg["role"], msg["content"])

    return converter


def export_jsonl(logfile: Path, output_path: Path = None,
                 update_index: bool = False, **kwargs) -> Path:
    """
    Export log file to JSONL format and optionally update index.

    Args:
        logfile: Source log file
        output_path: Destination path (auto-generated if not provided)
        update_index: Whether to update sessions-index.json
        **kwargs: Additional args for convert_to_jsonl (including meta dict)

    Returns:
        Path to the written JSONL file
    """
    converter = convert_to_jsonl(logfile, **kwargs)
    meta = kwargs.get("meta", {})

    # Determine output path
    if output_path is None:
        app = meta.get("app") or kwargs.get("app") or logfile.parent.name
        if app in ["raw", "sessions", "legacy"]:
            app = logfile.parent.parent.name

        sessions_dir = Path.home() / "ai_shell_logs" / app / "sessions"
        output_path = sessions_dir / f"{converter.session_id}.jsonl"

    # Write JSONL
    converter.write_jsonl(output_path)

    # Update index if requested
    if update_index and HAS_SESSION_SUPPORT:
        app = meta.get("app") or kwargs.get("app") or logfile.parent.name
        if app in ["raw", "sessions", "legacy"]:
            app = logfile.parent.parent.name

        index = SessionIndex(app)
        index.add_session(
            session_id=converter.session_id,
            jsonl_path=output_path,
            source_file=logfile,
            first_prompt=converter.first_prompt,
            message_count=converter.message_count,
            model=kwargs.get("model"),
            tag=meta.get("tag") or kwargs.get("tag"),
            cwd=meta.get("cwd") or kwargs.get("cwd"),
            git_branch=meta.get("gitBranch"),
            duration=meta.get("duration"),
            git_commits=meta.get("gitCommitsMade"),
            files_modified=meta.get("filesModified")
        )

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Convert AI session logs to clean text, JSON, or JSONL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    ai_export.py session.log                    # Clean text output
    ai_export.py session.log --json             # Legacy JSON format
    ai_export.py session.log --jsonl            # Claude-compatible JSONL
    ai_export.py session.log --jsonl --index    # JSONL + update session index
        """
    )
    parser.add_argument('logfile', type=Path, help='Path to the log file')
    parser.add_argument('--json', action='store_true',
                        help='Output as legacy JSON (deprecated, use --jsonl)')
    parser.add_argument('--jsonl', action='store_true',
                        help='Output as Claude-compatible JSONL')
    parser.add_argument('--index', action='store_true',
                        help='Update sessions-index.json (requires --jsonl)')
    parser.add_argument('-o', '--output', type=Path,
                        help='Output file (default: stdout or auto-generated for --jsonl)')
    parser.add_argument('--app', type=str,
                        help='App name (auto-detected from path)')
    parser.add_argument('--model', type=str,
                        help='Model name for metadata')
    parser.add_argument('--tag', type=str,
                        help='Session tag/description')
    parser.add_argument('--meta', type=Path,
                        help='Path to .meta file with session metadata')
    parser.add_argument('--cols', type=int, default=120,
                        help='Terminal columns (default: 120)')
    parser.add_argument('--rows', type=int, default=50,
                        help='Terminal rows (default: 50)')

    args = parser.parse_args()

    if not args.logfile.exists():
        print(f"Error: File not found: {args.logfile}", file=sys.stderr)
        sys.exit(1)

    # Handle JSONL output
    if args.jsonl:
        if not HAS_SESSION_SUPPORT:
            print("Error: session_converter.py required for --jsonl", file=sys.stderr)
            print("Make sure session_converter.py is in the same directory", file=sys.stderr)
            sys.exit(1)

        # Load metadata file if provided
        meta = None
        if args.meta and args.meta.exists():
            try:
                with open(args.meta) as f:
                    meta = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load metadata file: {e}", file=sys.stderr)

        try:
            output_path = export_jsonl(
                args.logfile,
                output_path=args.output,
                update_index=args.index,
                app=args.app,
                model=args.model,
                tag=args.tag,
                meta=meta
            )
            print(f"Written to: {output_path}", file=sys.stderr)

            # Also print session info
            converter = convert_to_jsonl(args.logfile, app=args.app, meta=meta)
            print(f"Session ID: {converter.session_id}", file=sys.stderr)
            print(f"Messages: {converter.message_count}", file=sys.stderr)

            if args.index:
                print("Index updated", file=sys.stderr)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        return

    # Render the log through terminal emulator
    rendered = render_log(args.logfile, args.cols, args.rows)

    if args.json:
        # Deprecation warning
        print("Warning: --json is deprecated, use --jsonl for new format",
              file=sys.stderr)

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
