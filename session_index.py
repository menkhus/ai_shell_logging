#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
session_index.py - Manage sessions-index.json for AI session logs

Provides atomic updates to the session index, supporting:
- Add/update session entries
- Remove sessions
- Query sessions by various criteria

Usage:
    from session_index import SessionIndex

    index = SessionIndex("ollama")
    index.add_session(
        session_id="abc-123",
        jsonl_path=Path("sessions/abc-123.jsonl"),
        source_file=Path("2026-01-24_121414.log"),
        first_prompt="How do I...",
        message_count=8,
        model="llama3"
    )
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field


@dataclass
class SessionEntry:
    """A single entry in the session index."""
    sessionId: str
    fullPath: str
    sourceFile: str
    firstPrompt: str
    messageCount: int
    created: str
    modified: str
    model: Optional[str] = None
    tag: Optional[str] = None
    cwd: Optional[str] = None
    gitBranch: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove None values
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionEntry':
        return cls(
            sessionId=data.get("sessionId", ""),
            fullPath=data.get("fullPath", ""),
            sourceFile=data.get("sourceFile", ""),
            firstPrompt=data.get("firstPrompt", ""),
            messageCount=data.get("messageCount", 0),
            created=data.get("created", ""),
            modified=data.get("modified", ""),
            model=data.get("model"),
            tag=data.get("tag"),
            cwd=data.get("cwd"),
            gitBranch=data.get("gitBranch")
        )


class SessionIndex:
    """
    Manage sessions-index.json for an app.

    Provides thread-safe, atomic updates to the session index.
    """

    VERSION = 1

    def __init__(self, app: str, base_dir: Path = None):
        """
        Initialize index manager.

        Args:
            app: Application name (ollama, gemini, etc.)
            base_dir: Base directory for logs (default: ~/ai_shell_logs)
        """
        self.app = app
        self.base_dir = base_dir or Path.home() / "ai_shell_logs"
        self.app_dir = self.base_dir / app
        self.index_path = self.app_dir / "sessions-index.json"
        self.sessions_dir = self.app_dir / "sessions"

        self._entries: List[SessionEntry] = []
        self._load()

    def _load(self):
        """Load index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path) as f:
                    data = json.load(f)
                self._entries = [
                    SessionEntry.from_dict(e)
                    for e in data.get("entries", [])
                ]
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load index {self.index_path}: {e}")
                self._entries = []
        else:
            self._entries = []

    def _save(self):
        """Save index to disk atomically."""
        self.app_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.VERSION,
            "app": self.app,
            "entries": [e.to_dict() for e in self._entries]
        }

        # Write atomically via temp file
        fd, temp_path = tempfile.mkstemp(
            dir=self.app_dir,
            prefix=".sessions-index-",
            suffix=".json"
        )
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.index_path)
        except:
            os.unlink(temp_path)
            raise

    @property
    def entries(self) -> List[SessionEntry]:
        """Get all entries (read-only copy)."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def get(self, session_id: str) -> Optional[SessionEntry]:
        """Get entry by session ID."""
        for entry in self._entries:
            if entry.sessionId == session_id:
                return entry
        return None

    def add_session(self, session_id: str, jsonl_path: Path,
                    source_file: Path, first_prompt: str,
                    message_count: int, model: str = None,
                    tag: str = None, cwd: str = None,
                    git_branch: str = None,
                    created: datetime = None,
                    modified: datetime = None):
        """
        Add or update a session entry.

        If session_id already exists, updates the entry.
        Otherwise, creates a new entry.
        """
        now = datetime.now().isoformat() + "Z"
        created_str = (created.isoformat() + "Z") if created else now
        modified_str = (modified.isoformat() + "Z") if modified else now

        entry = SessionEntry(
            sessionId=session_id,
            fullPath=str(jsonl_path.absolute()),
            sourceFile=str(source_file.absolute()) if source_file else "",
            firstPrompt=first_prompt[:100] if first_prompt else "",
            messageCount=message_count,
            created=created_str,
            modified=modified_str,
            model=model,
            tag=tag,
            cwd=cwd,
            gitBranch=git_branch
        )

        # Update existing or append
        existing_idx = next(
            (i for i, e in enumerate(self._entries) if e.sessionId == session_id),
            None
        )

        if existing_idx is not None:
            # Preserve original created time
            entry.created = self._entries[existing_idx].created
            self._entries[existing_idx] = entry
        else:
            self._entries.append(entry)

        self._save()
        return entry

    def remove_session(self, session_id: str) -> bool:
        """
        Remove a session from the index.

        Returns True if session was found and removed.
        """
        original_len = len(self._entries)
        self._entries = [e for e in self._entries if e.sessionId != session_id]

        if len(self._entries) < original_len:
            self._save()
            return True
        return False

    def find_by_source(self, source_file: Path) -> Optional[SessionEntry]:
        """Find entry by source file path."""
        source_str = str(source_file.absolute())
        for entry in self._entries:
            if entry.sourceFile == source_str:
                return entry
        return None

    def find_by_tag(self, tag_pattern: str) -> List[SessionEntry]:
        """Find entries matching tag pattern (case-insensitive)."""
        pattern = tag_pattern.lower()
        return [
            e for e in self._entries
            if e.tag and pattern in e.tag.lower()
        ]

    def find_by_prompt(self, prompt_pattern: str) -> List[SessionEntry]:
        """Find entries with first prompt matching pattern."""
        pattern = prompt_pattern.lower()
        return [
            e for e in self._entries
            if pattern in e.firstPrompt.lower()
        ]

    def recent(self, limit: int = 10) -> List[SessionEntry]:
        """Get most recent sessions by modified time."""
        sorted_entries = sorted(
            self._entries,
            key=lambda e: e.modified,
            reverse=True
        )
        return sorted_entries[:limit]

    def stats(self) -> dict:
        """Get index statistics."""
        total_messages = sum(e.messageCount for e in self._entries)
        models = {}
        for e in self._entries:
            if e.model:
                models[e.model] = models.get(e.model, 0) + 1

        return {
            "app": self.app,
            "session_count": len(self._entries),
            "total_messages": total_messages,
            "models": models,
            "index_path": str(self.index_path)
        }

    def rebuild_from_sessions(self):
        """
        Rebuild index by scanning sessions directory.

        Useful for recovery or after manual file operations.
        """
        self._entries = []

        if not self.sessions_dir.exists():
            self._save()
            return

        for jsonl_path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read first line (session meta)
                with open(jsonl_path) as f:
                    first_line = f.readline()
                    meta = json.loads(first_line)

                    # Count messages (remaining lines)
                    message_count = sum(1 for _ in f)

                if meta.get("type") == "session_meta":
                    entry = SessionEntry(
                        sessionId=meta.get("sessionId", jsonl_path.stem),
                        fullPath=str(jsonl_path.absolute()),
                        sourceFile=meta.get("sourceFile", ""),
                        firstPrompt="",  # Would need to read more to get this
                        messageCount=message_count,
                        created=meta.get("created", ""),
                        modified=meta.get("modified", ""),
                        model=meta.get("model"),
                        tag=meta.get("tag"),
                        cwd=meta.get("cwd")
                    )

                    # Try to get first prompt
                    with open(jsonl_path) as f:
                        f.readline()  # Skip meta
                        for line in f:
                            msg = json.loads(line)
                            if msg.get("type") == "user":
                                content = msg.get("message", {}).get("content", "")
                                entry.firstPrompt = content[:100]
                                break

                    self._entries.append(entry)

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not read {jsonl_path}: {e}")

        self._save()
        print(f"Rebuilt index with {len(self._entries)} sessions")


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Session index management")
    parser.add_argument("app", help="App name (ollama, gemini, etc.)")
    parser.add_argument("--list", "-l", action="store_true", help="List sessions")
    parser.add_argument("--recent", "-r", type=int, default=0, help="Show N recent")
    parser.add_argument("--stats", "-s", action="store_true", help="Show statistics")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild from sessions/")
    parser.add_argument("--find-tag", type=str, help="Find by tag")
    parser.add_argument("--find-prompt", type=str, help="Find by prompt")
    args = parser.parse_args()

    index = SessionIndex(args.app)

    if args.rebuild:
        index.rebuild_from_sessions()
    elif args.stats:
        stats = index.stats()
        print(f"App: {stats['app']}")
        print(f"Sessions: {stats['session_count']}")
        print(f"Total messages: {stats['total_messages']}")
        if stats['models']:
            print("Models:")
            for model, count in sorted(stats['models'].items(), key=lambda x: -x[1]):
                print(f"  {model}: {count}")
    elif args.find_tag:
        entries = index.find_by_tag(args.find_tag)
        for e in entries:
            print(f"{e.sessionId[:8]}  {e.tag}  {e.firstPrompt[:50]}...")
    elif args.find_prompt:
        entries = index.find_by_prompt(args.find_prompt)
        for e in entries:
            print(f"{e.sessionId[:8]}  {e.firstPrompt[:60]}...")
    elif args.recent > 0:
        entries = index.recent(args.recent)
        for e in entries:
            print(f"{e.modified[:10]}  {e.sessionId[:8]}  {e.firstPrompt[:50]}...")
    elif args.list:
        for e in index.entries:
            tag = f"[{e.tag}] " if e.tag else ""
            print(f"{e.sessionId[:8]}  {tag}{e.firstPrompt[:50]}...")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
