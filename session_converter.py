#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
session_converter.py - Convert parsed messages to Claude-compatible JSONL format

Implements deterministic UUID generation for idempotent reprocessing.

Usage:
    from session_converter import SessionConverter

    converter = SessionConverter(
        app="ollama",
        source_file=Path("2026-01-24_121414.log"),
        start_time=datetime(2026, 1, 24, 12, 14, 14)
    )
    converter.add_message("user", "How do I...")
    converter.add_message("assistant", "You can...")
    converter.write_jsonl(Path("sessions/abc123.jsonl"))
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import uuid5, UUID, NAMESPACE_URL
from dataclasses import dataclass, field, asdict


def generate_session_id(app: str, filename: str, start_time: datetime) -> str:
    """
    Generate deterministic session ID from source identity.

    Same inputs always produce the same UUID, enabling idempotent reprocessing.
    """
    key = f"{app}:{filename}:{start_time.isoformat()}"
    return str(uuid5(NAMESPACE_URL, key))


def generate_message_id(session_id: str, turn_number: int) -> str:
    """
    Generate deterministic message ID within a session.

    Uses session_id as namespace to ensure uniqueness across sessions.
    """
    return str(uuid5(UUID(session_id), f"turn:{turn_number}"))


@dataclass
class SessionMeta:
    """Metadata record for a session (first line of JSONL)."""
    type: str = "session_meta"
    sessionId: str = ""
    app: str = ""
    sourceFile: str = ""
    created: str = ""
    modified: str = ""
    messageCount: int = 0
    model: Optional[str] = None
    tag: Optional[str] = None
    cwd: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove None values for cleaner output
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class MessageRecord:
    """A single message record in JSONL format."""
    sessionId: str
    uuid: str
    parentUuid: Optional[str]
    timestamp: str
    type: str  # "user" or "assistant"
    message: Dict[str, str]  # {"role": "user"|"assistant", "content": "..."}

    def to_dict(self) -> dict:
        return asdict(self)


class SessionConverter:
    """
    Convert parsed conversation messages to Claude-compatible JSONL format.

    Handles:
    - Deterministic UUID generation (session and message IDs)
    - Parent chain threading (each message links to its predecessor)
    - JSONL output with session metadata header
    """

    def __init__(self, app: str, source_file: Path, start_time: datetime,
                 model: str = None, tag: str = None, cwd: str = None):
        """
        Initialize converter for a session.

        Args:
            app: Application name (ollama, gemini, etc.)
            source_file: Original log file path
            start_time: Session start timestamp
            model: Optional model name (llama3, gemini-pro, etc.)
            tag: Optional session tag/description
            cwd: Optional working directory
        """
        self.app = app
        self.source_file = source_file
        self.start_time = start_time
        self.model = model
        self.tag = tag
        self.cwd = cwd

        # Generate deterministic session ID
        self.session_id = generate_session_id(app, source_file.name, start_time)

        # Message storage
        self.messages: List[MessageRecord] = []

        # Track timestamps
        self._last_timestamp = start_time

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def first_prompt(self) -> str:
        """Get first user prompt for index."""
        for msg in self.messages:
            if msg.type == "user":
                return msg.message.get("content", "")[:100]
        return ""

    def add_message(self, role: str, content: str,
                    timestamp: datetime = None) -> MessageRecord:
        """
        Add a message with auto-generated UUID and parent chain.

        Args:
            role: "user" or "assistant"
            content: Message content
            timestamp: Optional timestamp (defaults to incrementing from start)

        Returns:
            The created MessageRecord
        """
        turn = len(self.messages)
        uuid = generate_message_id(self.session_id, turn)
        parent_uuid = self.messages[-1].uuid if self.messages else None

        # Handle timestamp
        if timestamp is None:
            timestamp = self._last_timestamp
        self._last_timestamp = timestamp

        record = MessageRecord(
            sessionId=self.session_id,
            uuid=uuid,
            parentUuid=parent_uuid,
            timestamp=timestamp.isoformat() + "Z",
            type=role,
            message={"role": role, "content": content}
        )

        self.messages.append(record)
        return record

    def get_session_meta(self) -> SessionMeta:
        """Generate session metadata record."""
        created = self.messages[0].timestamp if self.messages else self.start_time.isoformat() + "Z"
        modified = self.messages[-1].timestamp if self.messages else created

        return SessionMeta(
            sessionId=self.session_id,
            app=self.app,
            sourceFile=str(self.source_file),
            created=created,
            modified=modified,
            messageCount=len(self.messages),
            model=self.model,
            tag=self.tag,
            cwd=self.cwd
        )

    def to_jsonl(self) -> str:
        """Convert session to JSONL string."""
        lines = []

        # Session metadata first
        meta = self.get_session_meta()
        lines.append(json.dumps(meta.to_dict()))

        # Then each message
        for msg in self.messages:
            lines.append(json.dumps(msg.to_dict()))

        return "\n".join(lines) + "\n"

    def write_jsonl(self, output_path: Path) -> Path:
        """
        Write session as JSONL file.

        Args:
            output_path: Destination path for JSONL file

        Returns:
            The output path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            f.write(self.to_jsonl())

        return output_path

    @classmethod
    def from_messages(cls, app: str, source_file: Path, start_time: datetime,
                     messages: List[Dict[str, str]], **kwargs) -> 'SessionConverter':
        """
        Create converter from a list of message dicts.

        Args:
            app: Application name
            source_file: Original log file
            start_time: Session start time
            messages: List of {"role": "user"|"assistant", "content": "..."}
            **kwargs: Additional args (model, tag, cwd)

        Returns:
            SessionConverter with messages added
        """
        converter = cls(app, source_file, start_time, **kwargs)
        for msg in messages:
            converter.add_message(msg["role"], msg["content"])
        return converter


def parse_timestamp_from_filename(filename: str) -> datetime:
    """
    Parse timestamp from log filename format: YYYY-MM-DD_HHMMSS.log

    Args:
        filename: Log filename

    Returns:
        Parsed datetime
    """
    import re
    # Match YYYY-MM-DD_HHMMSS pattern
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})', filename)
    if match:
        year, month, day, hour, minute, second = map(int, match.groups())
        return datetime(year, month, day, hour, minute, second)

    # Fallback to file modification time or now
    return datetime.now()


# =============================================================================
# CLI for testing
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Session converter utilities")
    parser.add_argument("--test", action="store_true", help="Run test conversion")
    parser.add_argument("--uuid", type=str, help="Generate session UUID for given key")
    args = parser.parse_args()

    if args.uuid:
        # Generate UUID for testing
        session_id = str(uuid5(NAMESPACE_URL, args.uuid))
        print(f"Key: {args.uuid}")
        print(f"UUID: {session_id}")
    elif args.test:
        # Test conversion
        from datetime import datetime

        converter = SessionConverter(
            app="ollama",
            source_file=Path("2026-01-24_121414.log"),
            start_time=datetime(2026, 1, 24, 12, 14, 14),
            model="llama3"
        )

        converter.add_message("user", "How do I sort a list in Python?")
        converter.add_message("assistant", "You can use the sorted() function or the .sort() method...")
        converter.add_message("user", "What's the difference?")
        converter.add_message("assistant", "sorted() returns a new list, while .sort() modifies in place...")

        print("Session ID:", converter.session_id)
        print("Message count:", converter.message_count)
        print("First prompt:", converter.first_prompt)
        print()
        print("JSONL output:")
        print(converter.to_jsonl())

        # Verify idempotency
        converter2 = SessionConverter(
            app="ollama",
            source_file=Path("2026-01-24_121414.log"),
            start_time=datetime(2026, 1, 24, 12, 14, 14),
            model="llama3"
        )
        converter2.add_message("user", "How do I sort a list in Python?")

        print("Idempotency check:")
        print(f"  Session ID match: {converter.session_id == converter2.session_id}")
        print(f"  First message ID match: {converter.messages[0].uuid == converter2.messages[0].uuid}")
    else:
        parser.print_help()
