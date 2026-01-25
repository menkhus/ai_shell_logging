#!/usr/bin/env python3
# Copyright (c) 2026 Mark Menkhus <mark.menkhus@gmail.com>
# SPDX-License-Identifier: MIT
"""
enhanced_extractor.py - Deep extraction of all available data from Claude Code logs

Extracts the full richness of the log namespace including:
- Thinking blocks (Claude's reasoning)
- Tool timing and performance metrics
- Session metadata and context
- Error/retry patterns
- Progress and agent tracking
- Conversation flow and branching

Usage:
    enhanced_extractor.py                     # Extract from all sessions
    enhanced_extractor.py <jsonl_file>        # Extract from specific file
    enhanced_extractor.py --json              # Output raw JSON
    enhanced_extractor.py --report            # Human-readable report (default)
    enhanced_extractor.py --export <file>     # Export full data to JSON file
"""

import sys
import json
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class MessageNode:
    """Message in conversation tree for threading analysis."""
    session_id: str
    uuid: str
    parent_uuid: Optional[str] = None
    logical_parent_uuid: Optional[str] = None
    entry_type: Optional[str] = None  # user, assistant, etc.
    timestamp: Optional[str] = None
    depth: int = 0  # Computed tree depth
    is_branch_point: bool = False  # Has multiple children
    is_dead_end: bool = False  # Leaf with no meaningful outcome


@dataclass
class FileSnapshot:
    """File state at a checkpoint."""
    session_id: str
    timestamp: str
    message_id: str
    is_update: bool = False
    tracked_files: list = field(default_factory=list)  # List of file paths
    file_count: int = 0


@dataclass
class QueueOperation:
    """Queue operation for tool call tracking."""
    session_id: str
    timestamp: str
    operation: str  # enqueue, dequeue, remove, popAll
    content: Optional[str] = None
    tool_use_id: Optional[str] = None
    parent_tool_use_id: Optional[str] = None


@dataclass
class ThinkingMetadata:
    """Thinking intensity and triggers."""
    session_id: str
    timestamp: str
    level: str  # e.g., "high"
    disabled: bool = False
    triggers: list = field(default_factory=list)
    associated_uuid: Optional[str] = None


@dataclass
class TodoItem:
    """Task tracking item."""
    session_id: str
    timestamp: str
    content: str
    status: str  # pending, in_progress, completed
    active_form: Optional[str] = None


@dataclass
class ApiRequest:
    """API request tracking for correlation."""
    session_id: str
    timestamp: str
    request_id: str
    entry_type: str  # assistant, error, etc.
    has_error: bool = False
    model: Optional[str] = None
    stop_reason: Optional[str] = None


@dataclass
class ThinkingBlock:
    """Claude's internal reasoning."""
    session_id: str
    timestamp: str
    content: str
    char_count: int
    word_count: int
    preceding_user_message: Optional[str] = None
    following_action: Optional[str] = None  # tool name or text response


@dataclass
class ToolExecution:
    """Rich tool execution data."""
    session_id: str
    timestamp: str
    tool_name: str
    tool_id: str

    # Input data
    input_params: dict = field(default_factory=dict)

    # Result data
    success: bool = True
    is_error: bool = False
    error_message: Optional[str] = None

    # Performance metrics
    duration_ms: Optional[float] = None
    bytes_transferred: Optional[int] = None

    # Content metrics
    num_files: Optional[int] = None
    num_lines: Optional[int] = None
    truncated: bool = False

    # For edits
    structured_patch: Optional[dict] = None

    # For web operations
    retrieval_status: Optional[str] = None

    # Result content (truncated for storage)
    result_preview: Optional[str] = None


@dataclass
class TurnDuration:
    """Turn-level timing from system entries."""
    session_id: str
    timestamp: str
    duration_ms: float
    uuid: Optional[str] = None


@dataclass
class SessionMetadata:
    """Session-level context."""
    session_id: str
    first_timestamp: Optional[str] = None
    last_timestamp: Optional[str] = None
    cwd: Optional[str] = None
    version: Optional[str] = None
    git_branch: Optional[str] = None
    slug: Optional[str] = None

    # Counts
    user_messages: int = 0
    assistant_messages: int = 0
    tool_calls: int = 0
    thinking_blocks: int = 0
    errors: int = 0
    turns: int = 0

    # Tokens
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0

    # Timing
    total_turn_duration_ms: float = 0

    # Branching
    has_sidechains: bool = False
    agent_ids: list = field(default_factory=list)

    # Phase 1 additions
    max_conversation_depth: int = 0
    branch_count: int = 0
    dead_end_count: int = 0
    file_snapshots: int = 0
    queue_operations: int = 0
    todos_created: int = 0
    todos_completed: int = 0
    permission_mode: Optional[str] = None
    user_type: Optional[str] = None
    thinking_level: Optional[str] = None  # Most recent/common


@dataclass
class ErrorEvent:
    """Error and retry tracking."""
    session_id: str
    timestamp: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    retry_attempt: Optional[int] = None
    max_retries: Optional[int] = None
    retry_in_ms: Optional[int] = None
    cause: Optional[str] = None


@dataclass
class ProgressEvent:
    """Agent progress tracking."""
    session_id: str
    timestamp: str
    agent_id: Optional[str] = None
    tool_name: Optional[str] = None
    status: Optional[str] = None
    elapsed_ms: Optional[float] = None
    output_preview: Optional[str] = None
    task_type: Optional[str] = None


@dataclass
class SummaryEvent:
    """Conversation summarization."""
    session_id: str
    timestamp: str
    summary_text: Optional[str] = None
    leaf_uuid: Optional[str] = None


@dataclass
class ExtractedData:
    """All extracted data from logs."""
    sessions: dict = field(default_factory=dict)  # session_id -> SessionMetadata
    thinking_blocks: list = field(default_factory=list)
    tool_executions: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    progress_events: list = field(default_factory=list)
    summaries: list = field(default_factory=list)
    turn_durations: list = field(default_factory=list)

    # Phase 1 additions
    message_nodes: list = field(default_factory=list)  # For threading
    file_snapshots: list = field(default_factory=list)
    queue_operations: list = field(default_factory=list)
    thinking_metadata: list = field(default_factory=list)
    todos: list = field(default_factory=list)
    api_requests: list = field(default_factory=list)  # requestId tracking

    # Aggregates
    tool_timing: dict = field(default_factory=lambda: defaultdict(list))
    thinking_patterns: dict = field(default_factory=dict)
    conversation_trees: dict = field(default_factory=dict)  # session_id -> tree structure


def extract_from_session(jsonl_path: Path) -> ExtractedData:
    """Extract all data from a single session file."""
    data = ExtractedData()

    session_id = None
    session_meta = None
    last_user_message = None
    pending_tool_calls = {}  # tool_id -> ToolExecution

    entries = []
    with open(jsonl_path) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    for i, entry in enumerate(entries):
        entry_type = entry.get('type')
        timestamp = entry.get('timestamp', '')

        # Extract session ID and metadata
        if 'sessionId' in entry:
            session_id = entry['sessionId']
            if session_id not in data.sessions:
                data.sessions[session_id] = SessionMetadata(session_id=session_id)
            session_meta = data.sessions[session_id]

            # Update metadata
            if entry.get('cwd'):
                session_meta.cwd = entry['cwd']
            if entry.get('version'):
                session_meta.version = entry['version']
            if entry.get('gitBranch'):
                session_meta.git_branch = entry['gitBranch']
            if entry.get('slug'):
                session_meta.slug = entry['slug']
            if entry.get('isSidechain'):
                session_meta.has_sidechains = True
            if entry.get('agentId') and entry['agentId'] not in session_meta.agent_ids:
                session_meta.agent_ids.append(entry['agentId'])

            # Track timestamps
            if timestamp:
                if not session_meta.first_timestamp:
                    session_meta.first_timestamp = timestamp
                session_meta.last_timestamp = timestamp

        # Process by entry type
        if entry_type == 'user':
            if session_meta:
                session_meta.user_messages += 1
            msg = entry.get('message', {})
            content = msg.get('content', '')
            if isinstance(content, str):
                last_user_message = content[:500]
            elif isinstance(content, list):
                texts = [c.get('text', '') for c in content if isinstance(c, dict) and c.get('type') == 'text']
                last_user_message = ' '.join(texts)[:500]

        elif entry_type == 'assistant':
            if session_meta:
                session_meta.assistant_messages += 1

            msg = entry.get('message', {})

            # Extract token usage
            usage = msg.get('usage', {})
            if usage and session_meta:
                session_meta.total_input_tokens += usage.get('input_tokens', 0)
                session_meta.total_output_tokens += usage.get('output_tokens', 0)
                session_meta.total_cache_read += usage.get('cache_read_input_tokens', 0)
                session_meta.total_cache_write += usage.get('cache_creation_input_tokens', 0)

            # Process content
            content = msg.get('content', [])
            if isinstance(content, list):
                for j, item in enumerate(content):
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get('type')

                    # Thinking blocks
                    if item_type == 'thinking':
                        thinking_text = item.get('thinking', '')

                        # Determine following action
                        following_action = None
                        for k in range(j + 1, len(content)):
                            next_item = content[k]
                            if isinstance(next_item, dict):
                                if next_item.get('type') == 'tool_use':
                                    following_action = next_item.get('name')
                                    break
                                elif next_item.get('type') == 'text':
                                    following_action = 'text_response'
                                    break

                        tb = ThinkingBlock(
                            session_id=session_id or '',
                            timestamp=timestamp,
                            content=thinking_text,
                            char_count=len(thinking_text),
                            word_count=len(thinking_text.split()),
                            preceding_user_message=last_user_message,
                            following_action=following_action
                        )
                        data.thinking_blocks.append(tb)
                        if session_meta:
                            session_meta.thinking_blocks += 1

                    # Tool use
                    elif item_type == 'tool_use':
                        tool_id = item.get('id', '')
                        tool_name = item.get('name', '')

                        te = ToolExecution(
                            session_id=session_id or '',
                            timestamp=timestamp,
                            tool_name=tool_name,
                            tool_id=tool_id,
                            input_params=item.get('input', {})
                        )
                        pending_tool_calls[tool_id] = te
                        if session_meta:
                            session_meta.tool_calls += 1

                    # Tool result
                    elif item_type == 'tool_result':
                        tool_id = item.get('tool_use_id', '')
                        if tool_id in pending_tool_calls:
                            te = pending_tool_calls.pop(tool_id)
                            te.is_error = item.get('is_error', False)

                            result_content = item.get('content', '')
                            if isinstance(result_content, str):
                                te.result_preview = result_content[:500]

                            if te.is_error and session_meta:
                                session_meta.errors += 1

                            data.tool_executions.append(te)

            # Process toolUseResult (rich metadata)
            tool_result = entry.get('toolUseResult', {})
            if tool_result:
                # Find matching tool execution and enrich it
                for te in reversed(data.tool_executions):
                    if te.session_id == session_id:
                        # Enrich with timing data
                        if 'durationMs' in tool_result:
                            te.duration_ms = tool_result['durationMs']
                            data.tool_timing[te.tool_name].append(te.duration_ms)
                        if 'bytes' in tool_result:
                            te.bytes_transferred = tool_result['bytes']
                        if 'numFiles' in tool_result:
                            te.num_files = tool_result['numFiles']
                        if 'numLines' in tool_result:
                            te.num_lines = tool_result['numLines']
                        if tool_result.get('truncated'):
                            te.truncated = True
                        if 'structuredPatch' in tool_result:
                            te.structured_patch = tool_result['structuredPatch']
                        if 'retrieval_status' in tool_result:
                            te.retrieval_status = tool_result['retrieval_status']
                        break

            # Extract requestId for API tracking
            if entry.get('requestId'):
                ar = ApiRequest(
                    session_id=session_id or '',
                    timestamp=timestamp,
                    request_id=entry['requestId'],
                    entry_type=entry_type,
                    has_error=entry.get('isApiErrorMessage', False),
                    model=msg.get('model'),
                    stop_reason=msg.get('stop_reason')
                )
                data.api_requests.append(ar)

        elif entry_type == 'progress':
            prog_data = entry.get('data', {})
            pe = ProgressEvent(
                session_id=session_id or '',
                timestamp=timestamp,
                agent_id=prog_data.get('agentId'),
                tool_name=prog_data.get('toolName'),
                status=prog_data.get('status'),
                elapsed_ms=prog_data.get('elapsedTimeMs'),
                output_preview=str(prog_data.get('output', ''))[:200],
                task_type=prog_data.get('taskType')
            )
            data.progress_events.append(pe)

        elif entry_type == 'summary':
            se = SummaryEvent(
                session_id=session_id or '',
                timestamp=timestamp,
                summary_text=entry.get('summary', '')[:1000],
                leaf_uuid=entry.get('leafUuid')
            )
            data.summaries.append(se)

        elif entry_type == 'system' and entry.get('subtype') == 'turn_duration':
            duration_ms = entry.get('durationMs', 0)
            td = TurnDuration(
                session_id=session_id or '',
                timestamp=timestamp,
                duration_ms=duration_ms,
                uuid=entry.get('uuid')
            )
            data.turn_durations.append(td)
            if session_meta:
                session_meta.turns += 1
                session_meta.total_turn_duration_ms += duration_ms

        # Phase 1: File history snapshots
        elif entry_type == 'file-history-snapshot':
            snapshot_data = entry.get('snapshot', {})
            tracked = snapshot_data.get('trackedFileBackups', {})
            fs = FileSnapshot(
                session_id=session_id or '',
                timestamp=timestamp,
                message_id=entry.get('messageId', ''),
                is_update=entry.get('isSnapshotUpdate', False),
                tracked_files=list(tracked.keys()) if isinstance(tracked, dict) else [],
                file_count=len(tracked) if isinstance(tracked, dict) else 0
            )
            data.file_snapshots.append(fs)
            if session_meta:
                session_meta.file_snapshots += 1

        # Phase 1: Queue operations
        elif entry_type == 'queue-operation':
            qo = QueueOperation(
                session_id=session_id or '',
                timestamp=timestamp,
                operation=entry.get('operation', ''),
                content=str(entry.get('content', ''))[:500] if entry.get('content') else None,
                tool_use_id=entry.get('toolUseID'),
                parent_tool_use_id=entry.get('parentToolUseID')
            )
            data.queue_operations.append(qo)
            if session_meta:
                session_meta.queue_operations += 1

        # Phase 1: Extract threading info from all entries with uuid
        if entry.get('uuid'):
            node = MessageNode(
                session_id=session_id or '',
                uuid=entry['uuid'],
                parent_uuid=entry.get('parentUuid'),
                logical_parent_uuid=entry.get('logicalParentUuid'),
                entry_type=entry_type,
                timestamp=timestamp
            )
            data.message_nodes.append(node)

        # Phase 1: Thinking metadata (on user entries)
        if entry.get('thinkingMetadata'):
            tm_data = entry['thinkingMetadata']
            tm = ThinkingMetadata(
                session_id=session_id or '',
                timestamp=timestamp,
                level=tm_data.get('level', ''),
                disabled=tm_data.get('disabled', False),
                triggers=tm_data.get('triggers', []),
                associated_uuid=entry.get('uuid')
            )
            data.thinking_metadata.append(tm)
            if session_meta and tm.level:
                session_meta.thinking_level = tm.level

        # Phase 1: Todos
        if entry.get('todos'):
            for todo in entry['todos']:
                if isinstance(todo, dict):
                    ti = TodoItem(
                        session_id=session_id or '',
                        timestamp=timestamp,
                        content=todo.get('content', '')[:200],
                        status=todo.get('status', ''),
                        active_form=todo.get('activeForm')
                    )
                    data.todos.append(ti)
                    if session_meta:
                        session_meta.todos_created += 1
                        if ti.status == 'completed':
                            session_meta.todos_completed += 1

        # Phase 1: Permission mode and user type
        if entry.get('permissionMode') and session_meta:
            session_meta.permission_mode = entry['permissionMode']
        if entry.get('userType') and session_meta:
            session_meta.user_type = entry['userType']

        # Error tracking
        if entry.get('error') or entry.get('isApiErrorMessage'):
            error_obj = entry.get('error', {})
            ee = ErrorEvent(
                session_id=session_id or '',
                timestamp=timestamp,
                error_message=error_obj.get('message') if isinstance(error_obj, dict) else str(error_obj),
                status_code=error_obj.get('status') if isinstance(error_obj, dict) else None,
                request_id=error_obj.get('requestID') if isinstance(error_obj, dict) else None,
                retry_attempt=entry.get('retryAttempt'),
                max_retries=entry.get('maxRetries'),
                retry_in_ms=entry.get('retryInMs'),
                cause=str(error_obj.get('cause', ''))[:200] if isinstance(error_obj, dict) else None
            )
            data.errors.append(ee)

    # Add any remaining pending tool calls
    for te in pending_tool_calls.values():
        data.tool_executions.append(te)

    return data


def merge_extracted_data(all_data: list) -> ExtractedData:
    """Merge multiple ExtractedData objects."""
    merged = ExtractedData()

    for data in all_data:
        merged.sessions.update(data.sessions)
        merged.thinking_blocks.extend(data.thinking_blocks)
        merged.tool_executions.extend(data.tool_executions)
        merged.errors.extend(data.errors)
        merged.progress_events.extend(data.progress_events)
        merged.summaries.extend(data.summaries)
        merged.turn_durations.extend(data.turn_durations)

        # Phase 1 additions
        merged.message_nodes.extend(data.message_nodes)
        merged.file_snapshots.extend(data.file_snapshots)
        merged.queue_operations.extend(data.queue_operations)
        merged.thinking_metadata.extend(data.thinking_metadata)
        merged.todos.extend(data.todos)
        merged.api_requests.extend(data.api_requests)

        for tool, timings in data.tool_timing.items():
            merged.tool_timing[tool].extend(timings)

    return merged


def compute_conversation_trees(data: ExtractedData) -> dict:
    """Compute conversation tree structure and metrics from message nodes."""
    trees = {}  # session_id -> tree info

    # Group nodes by session
    session_nodes = defaultdict(list)
    for node in data.message_nodes:
        session_nodes[node.session_id].append(node)

    for session_id, nodes in session_nodes.items():
        # Build parent-child map
        uuid_to_node = {n.uuid: n for n in nodes}
        children = defaultdict(list)
        roots = []

        for node in nodes:
            if node.parent_uuid and node.parent_uuid in uuid_to_node:
                children[node.parent_uuid].append(node.uuid)
            elif not node.parent_uuid:
                roots.append(node.uuid)

        # Compute depths via BFS
        depths = {}
        queue = [(r, 0) for r in roots]
        max_depth = 0
        while queue:
            uuid, depth = queue.pop(0)
            depths[uuid] = depth
            max_depth = max(max_depth, depth)
            for child in children[uuid]:
                queue.append((child, depth + 1))

        # Identify branch points (nodes with >1 child)
        branch_points = [uuid for uuid, kids in children.items() if len(kids) > 1]

        # Identify dead ends (leaf nodes that are user type - no response)
        leaves = [n.uuid for n in nodes if n.uuid not in children]
        dead_ends = [uuid for uuid in leaves
                     if uuid in uuid_to_node and uuid_to_node[uuid].entry_type == 'user']

        trees[session_id] = {
            "node_count": len(nodes),
            "max_depth": max_depth,
            "branch_points": len(branch_points),
            "dead_ends": len(dead_ends),
            "roots": len(roots)
        }

        # Update session metadata
        if session_id in data.sessions:
            data.sessions[session_id].max_conversation_depth = max_depth
            data.sessions[session_id].branch_count = len(branch_points)
            data.sessions[session_id].dead_end_count = len(dead_ends)

    return trees


def compute_analytics(data: ExtractedData) -> dict:
    """Compute analytics from extracted data."""
    analytics = {
        "overview": {
            "total_sessions": len(data.sessions),
            "total_turns": len(data.turn_durations),
            "total_thinking_blocks": len(data.thinking_blocks),
            "total_tool_executions": len(data.tool_executions),
            "total_errors": len(data.errors),
            "total_progress_events": len(data.progress_events),
            "total_summaries": len(data.summaries)
        },
        "tokens": {
            "total_input": sum(s.total_input_tokens for s in data.sessions.values()),
            "total_output": sum(s.total_output_tokens for s in data.sessions.values()),
            "total_cache_read": sum(s.total_cache_read for s in data.sessions.values()),
            "total_cache_write": sum(s.total_cache_write for s in data.sessions.values())
        },
        "thinking": {},
        "tool_performance": {},
        "errors": {},
        "agents": {}
    }

    # Thinking analytics
    if data.thinking_blocks:
        total_chars = sum(tb.char_count for tb in data.thinking_blocks)
        total_words = sum(tb.word_count for tb in data.thinking_blocks)

        # Group by following action
        action_counts = defaultdict(int)
        action_thinking = defaultdict(list)
        for tb in data.thinking_blocks:
            action = tb.following_action or 'none'
            action_counts[action] += 1
            action_thinking[action].append(tb.char_count)

        analytics["thinking"] = {
            "total_chars": total_chars,
            "total_words": total_words,
            "avg_chars_per_block": total_chars // len(data.thinking_blocks) if data.thinking_blocks else 0,
            "avg_words_per_block": total_words // len(data.thinking_blocks) if data.thinking_blocks else 0,
            "by_following_action": {
                action: {
                    "count": count,
                    "avg_chars": sum(action_thinking[action]) // count if count else 0
                }
                for action, count in action_counts.items()
            }
        }

    # Tool performance analytics
    for tool, timings in data.tool_timing.items():
        if timings:
            analytics["tool_performance"][tool] = {
                "count": len(timings),
                "avg_ms": sum(timings) / len(timings),
                "min_ms": min(timings),
                "max_ms": max(timings),
                "total_ms": sum(timings)
            }

    # Tool usage by type
    tool_counts = defaultdict(int)
    tool_errors = defaultdict(int)
    tool_bytes = defaultdict(int)
    for te in data.tool_executions:
        tool_counts[te.tool_name] += 1
        if te.is_error:
            tool_errors[te.tool_name] += 1
        if te.bytes_transferred:
            tool_bytes[te.tool_name] += te.bytes_transferred

    analytics["tool_usage"] = {
        tool: {
            "count": count,
            "errors": tool_errors[tool],
            "error_rate": tool_errors[tool] / count if count else 0,
            "total_bytes": tool_bytes[tool]
        }
        for tool, count in tool_counts.items()
    }

    # Error analytics
    error_types = defaultdict(int)
    retry_counts = []
    for err in data.errors:
        if err.status_code:
            error_types[f"HTTP {err.status_code}"] += 1
        if err.retry_attempt:
            retry_counts.append(err.retry_attempt)

    analytics["errors"] = {
        "total": len(data.errors),
        "by_type": dict(error_types),
        "avg_retries": sum(retry_counts) / len(retry_counts) if retry_counts else 0
    }

    # Agent analytics
    agent_sessions = defaultdict(int)
    for session in data.sessions.values():
        for agent_id in session.agent_ids:
            agent_sessions[agent_id] += 1

    analytics["agents"] = {
        "unique_agents": len(agent_sessions),
        "sessions_with_agents": sum(1 for s in data.sessions.values() if s.agent_ids),
        "by_agent": dict(agent_sessions)
    }

    # Version distribution
    version_counts = defaultdict(int)
    for session in data.sessions.values():
        if session.version:
            version_counts[session.version] += 1
    analytics["versions"] = dict(version_counts)

    # Git branch distribution
    branch_counts = defaultdict(int)
    for session in data.sessions.values():
        if session.git_branch:
            branch_counts[session.git_branch] += 1
    analytics["branches"] = dict(branch_counts)

    # Turn timing analytics
    if data.turn_durations:
        durations = [td.duration_ms for td in data.turn_durations]
        total_turns = len(durations)
        total_time_ms = sum(durations)

        analytics["turn_timing"] = {
            "total_turns": total_turns,
            "total_time_ms": total_time_ms,
            "total_time_minutes": total_time_ms / 60000,
            "avg_turn_ms": total_time_ms / total_turns if total_turns else 0,
            "min_turn_ms": min(durations),
            "max_turn_ms": max(durations),
            "median_turn_ms": sorted(durations)[total_turns // 2] if total_turns else 0
        }

        # Distribution buckets
        buckets = {"<1s": 0, "1-5s": 0, "5-30s": 0, "30s-2m": 0, ">2m": 0}
        for d in durations:
            if d < 1000:
                buckets["<1s"] += 1
            elif d < 5000:
                buckets["1-5s"] += 1
            elif d < 30000:
                buckets["5-30s"] += 1
            elif d < 120000:
                buckets["30s-2m"] += 1
            else:
                buckets[">2m"] += 1
        analytics["turn_timing"]["distribution"] = buckets

    # Phase 1: Conversation threading analytics
    if data.message_nodes:
        total_depth = sum(s.max_conversation_depth for s in data.sessions.values())
        total_branches = sum(s.branch_count for s in data.sessions.values())
        total_dead_ends = sum(s.dead_end_count for s in data.sessions.values())

        analytics["threading"] = {
            "total_messages": len(data.message_nodes),
            "avg_depth": total_depth / len(data.sessions) if data.sessions else 0,
            "max_depth": max((s.max_conversation_depth for s in data.sessions.values()), default=0),
            "total_branches": total_branches,
            "total_dead_ends": total_dead_ends,
            "sessions_with_branches": sum(1 for s in data.sessions.values() if s.branch_count > 0)
        }

    # Phase 1: File snapshot analytics
    if data.file_snapshots:
        # Count unique files across all snapshots
        all_files = set()
        for fs in data.file_snapshots:
            all_files.update(fs.tracked_files)

        # File frequency
        file_freq = defaultdict(int)
        for fs in data.file_snapshots:
            for f in fs.tracked_files:
                file_freq[f] += 1

        top_files = sorted(file_freq.items(), key=lambda x: -x[1])[:10]

        analytics["file_snapshots"] = {
            "total_snapshots": len(data.file_snapshots),
            "unique_files_tracked": len(all_files),
            "updates_vs_new": sum(1 for fs in data.file_snapshots if fs.is_update),
            "top_modified_files": dict(top_files)
        }

    # Phase 1: Queue operation analytics
    if data.queue_operations:
        op_counts = defaultdict(int)
        for qo in data.queue_operations:
            op_counts[qo.operation] += 1

        analytics["queue_operations"] = {
            "total": len(data.queue_operations),
            "by_operation": dict(op_counts),
            "enqueue_dequeue_ratio": op_counts.get('enqueue', 0) / op_counts.get('dequeue', 1) if op_counts.get('dequeue') else 0
        }

    # Phase 1: Thinking metadata analytics
    if data.thinking_metadata:
        level_counts = defaultdict(int)
        trigger_counts = defaultdict(int)
        for tm in data.thinking_metadata:
            level_counts[tm.level] += 1
            for trigger in tm.triggers:
                trigger_counts[trigger] += 1

        analytics["thinking_metadata"] = {
            "total_entries": len(data.thinking_metadata),
            "by_level": dict(level_counts),
            "by_trigger": dict(trigger_counts),
            "disabled_count": sum(1 for tm in data.thinking_metadata if tm.disabled)
        }

    # Phase 1: Todo analytics
    if data.todos:
        status_counts = defaultdict(int)
        for todo in data.todos:
            status_counts[todo.status] += 1

        analytics["todos"] = {
            "total": len(data.todos),
            "by_status": dict(status_counts),
            "completion_rate": status_counts.get('completed', 0) / len(data.todos) * 100 if data.todos else 0
        }

    # Phase 1: Permission and user type analytics
    perm_counts = defaultdict(int)
    user_type_counts = defaultdict(int)
    for session in data.sessions.values():
        if session.permission_mode:
            perm_counts[session.permission_mode] += 1
        if session.user_type:
            user_type_counts[session.user_type] += 1

    if perm_counts or user_type_counts:
        analytics["user_context"] = {
            "permission_modes": dict(perm_counts),
            "user_types": dict(user_type_counts)
        }

    # Phase 1: API request analytics
    if data.api_requests:
        error_requests = [ar for ar in data.api_requests if ar.has_error]
        models = defaultdict(int)
        stop_reasons = defaultdict(int)
        for ar in data.api_requests:
            if ar.model:
                models[ar.model] += 1
            if ar.stop_reason:
                stop_reasons[ar.stop_reason] += 1

        analytics["api_requests"] = {
            "total": len(data.api_requests),
            "unique_request_ids": len(set(ar.request_id for ar in data.api_requests)),
            "error_requests": len(error_requests),
            "error_rate": len(error_requests) / len(data.api_requests) * 100 if data.api_requests else 0,
            "by_model": dict(models),
            "by_stop_reason": dict(stop_reasons)
        }

    # =========================================================================
    # PHASE 2: VALUE EXTRACTION ANALYTICS
    # =========================================================================

    # 2.1 Efficiency Metrics
    efficiency = {"sessions": []}
    for session_id, session in data.sessions.items():
        total_tokens = session.total_input_tokens + session.total_output_tokens
        # Efficiency = how much work per token
        tokens_per_tool = total_tokens / session.tool_calls if session.tool_calls else 0
        tokens_per_turn = total_tokens / session.turns if session.turns else 0

        # Thinking efficiency
        thinking_per_tool = 0
        session_thinking = [tb for tb in data.thinking_blocks if tb.session_id == session_id]
        if session_thinking and session.tool_calls:
            total_thinking_chars = sum(tb.char_count for tb in session_thinking)
            thinking_per_tool = total_thinking_chars / session.tool_calls

        # Cache efficiency
        cache_rate = session.total_cache_read / session.total_input_tokens * 100 if session.total_input_tokens else 0

        # Time efficiency (ms per tool call)
        time_per_tool = session.total_turn_duration_ms / session.tool_calls if session.tool_calls else 0

        eff = {
            "session_id": session_id[:8],
            "tokens_per_tool": round(tokens_per_tool),
            "tokens_per_turn": round(tokens_per_turn),
            "thinking_per_tool": round(thinking_per_tool),
            "cache_rate": round(cache_rate, 1),
            "time_per_tool_ms": round(time_per_tool),
            "tool_calls": session.tool_calls,
            "turns": session.turns,
            "total_tokens": total_tokens
        }
        efficiency["sessions"].append(eff)

    # Aggregate efficiency metrics
    if efficiency["sessions"]:
        efficiency["avg_tokens_per_tool"] = sum(e["tokens_per_tool"] for e in efficiency["sessions"]) / len(efficiency["sessions"])
        efficiency["avg_cache_rate"] = sum(e["cache_rate"] for e in efficiency["sessions"]) / len(efficiency["sessions"])
        efficiency["avg_time_per_tool_ms"] = sum(e["time_per_tool_ms"] for e in efficiency["sessions"]) / len(efficiency["sessions"])

        # Identify outliers (inefficient sessions)
        sorted_by_tokens = sorted(efficiency["sessions"], key=lambda x: -x["tokens_per_tool"])
        efficiency["most_token_heavy"] = sorted_by_tokens[:5]
        efficiency["most_efficient"] = sorted_by_tokens[-5:]

    analytics["efficiency"] = efficiency

    # 2.2 Error Intelligence
    error_intel = {
        "by_hour": defaultdict(int),
        "by_version": defaultdict(int),
        "recovery_patterns": [],
        "error_sessions": []
    }

    for err in data.errors:
        # By hour
        if err.timestamp:
            try:
                hour = err.timestamp.split("T")[1][:2]
                error_intel["by_hour"][hour] += 1
            except:
                pass

        # Find session version
        if err.session_id in data.sessions:
            version = data.sessions[err.session_id].version or "unknown"
            error_intel["by_version"][version] += 1

    # Identify sessions with errors and their recovery
    error_session_ids = set(err.session_id for err in data.errors)
    for session_id in error_session_ids:
        session = data.sessions.get(session_id)
        if session:
            session_errors = [e for e in data.errors if e.session_id == session_id]
            # Check if session continued after errors (recovery)
            error_times = [e.timestamp for e in session_errors if e.timestamp]
            continued = session.last_timestamp and error_times and session.last_timestamp > max(error_times)

            error_intel["error_sessions"].append({
                "session_id": session_id[:8],
                "error_count": len(session_errors),
                "recovered": continued,
                "version": session.version
            })

    error_intel["by_hour"] = dict(error_intel["by_hour"])
    error_intel["by_version"] = dict(error_intel["by_version"])
    error_intel["recovery_rate"] = sum(1 for s in error_intel["error_sessions"] if s["recovered"]) / len(error_intel["error_sessions"]) * 100 if error_intel["error_sessions"] else 0

    analytics["error_intelligence"] = error_intel

    # 2.3 Conversation Flow
    flow = {
        "sidechain_sessions": [],
        "summarization_triggers": [],
        "depth_distribution": {"shallow": 0, "medium": 0, "deep": 0, "very_deep": 0}
    }

    for session_id, session in data.sessions.items():
        if session.has_sidechains:
            flow["sidechain_sessions"].append({
                "session_id": session_id[:8],
                "branches": session.branch_count,
                "depth": session.max_conversation_depth
            })

        # Depth distribution
        depth = session.max_conversation_depth
        if depth < 20:
            flow["depth_distribution"]["shallow"] += 1
        elif depth < 50:
            flow["depth_distribution"]["medium"] += 1
        elif depth < 150:
            flow["depth_distribution"]["deep"] += 1
        else:
            flow["depth_distribution"]["very_deep"] += 1

    # Summarization analysis
    for summary in data.summaries:
        session = data.sessions.get(summary.session_id)
        if session:
            flow["summarization_triggers"].append({
                "session_id": summary.session_id[:8],
                "at_depth": session.max_conversation_depth,
                "total_tokens_at_summary": session.total_input_tokens + session.total_output_tokens
            })

    flow["avg_depth_at_summary"] = sum(s["at_depth"] for s in flow["summarization_triggers"]) / len(flow["summarization_triggers"]) if flow["summarization_triggers"] else 0

    analytics["conversation_flow"] = flow

    # 2.4 Tool Effectiveness
    tool_eff = {
        "sequences": defaultdict(int),  # tool A -> tool B
        "latency_by_tool": {},
        "potential_redundancy": []
    }

    # Build tool sequences
    prev_tool = None
    prev_session = None
    for te in sorted(data.tool_executions, key=lambda x: x.timestamp):
        if te.session_id == prev_session and prev_tool:
            seq = f"{prev_tool} -> {te.tool_name}"
            tool_eff["sequences"][seq] += 1
        prev_tool = te.tool_name
        prev_session = te.session_id

    # Find common sequences
    top_sequences = sorted(tool_eff["sequences"].items(), key=lambda x: -x[1])[:20]
    tool_eff["top_sequences"] = dict(top_sequences)

    # Detect potential redundancy (same tool called multiple times in quick succession)
    tool_runs = []
    current_run = {"tool": None, "count": 0, "session": None}
    for te in sorted(data.tool_executions, key=lambda x: (x.session_id, x.timestamp)):
        if te.tool_name == current_run["tool"] and te.session_id == current_run["session"]:
            current_run["count"] += 1
        else:
            if current_run["count"] > 2:
                tool_runs.append({"tool": current_run["tool"], "consecutive": current_run["count"]})
            current_run = {"tool": te.tool_name, "count": 1, "session": te.session_id}

    # Count redundant patterns
    redundancy_by_tool = defaultdict(int)
    for run in tool_runs:
        redundancy_by_tool[run["tool"]] += run["consecutive"] - 1  # Extra calls beyond first

    tool_eff["redundant_calls"] = dict(redundancy_by_tool)
    tool_eff["total_redundant"] = sum(redundancy_by_tool.values())

    # Latency percentiles by tool
    for tool, timings in data.tool_timing.items():
        if timings:
            sorted_t = sorted(timings)
            n = len(sorted_t)
            tool_eff["latency_by_tool"][tool] = {
                "p50": sorted_t[n // 2],
                "p90": sorted_t[int(n * 0.9)] if n >= 10 else sorted_t[-1],
                "p99": sorted_t[int(n * 0.99)] if n >= 100 else sorted_t[-1]
            }

    del tool_eff["sequences"]  # Remove raw data, keep top_sequences
    analytics["tool_effectiveness"] = tool_eff

    # 2.5 Thinking Efficiency
    thinking_eff = {
        "wasted_thinking": 0,  # Thinking with no following action
        "thinking_before_errors": 0,
        "by_outcome": defaultdict(list)
    }

    for tb in data.thinking_blocks:
        if tb.following_action is None or tb.following_action == "none":
            thinking_eff["wasted_thinking"] += 1

        # Track thinking size by outcome type
        action = tb.following_action or "none"
        thinking_eff["by_outcome"][action].append(tb.char_count)

    # Compute averages by outcome
    thinking_eff["avg_by_outcome"] = {}
    for action, sizes in thinking_eff["by_outcome"].items():
        thinking_eff["avg_by_outcome"][action] = round(sum(sizes) / len(sizes)) if sizes else 0

    thinking_eff["wasted_thinking_pct"] = thinking_eff["wasted_thinking"] / len(data.thinking_blocks) * 100 if data.thinking_blocks else 0
    del thinking_eff["by_outcome"]  # Remove raw data

    analytics["thinking_efficiency"] = thinking_eff

    # 2.6 Session Characterization
    session_char = {
        "complexity_scores": [],
        "outcome_classification": {"productive": 0, "exploratory": 0, "struggling": 0},
        "project_types": defaultdict(int)
    }

    for session_id, session in data.sessions.items():
        # Complexity score: weighted combination of factors
        complexity = (
            session.tool_calls * 1.0 +
            session.branch_count * 5.0 +
            session.max_conversation_depth * 0.1 +
            (session.total_input_tokens + session.total_output_tokens) / 10000
        )

        # Outcome classification based on patterns
        error_count = len([e for e in data.errors if e.session_id == session_id])
        todo_completion = session.todos_completed / session.todos_created if session.todos_created else 1

        if error_count > 5 or (session.dead_end_count > 2):
            outcome = "struggling"
        elif session.branch_count > 5 or todo_completion < 0.3:
            outcome = "exploratory"
        else:
            outcome = "productive"

        session_char["outcome_classification"][outcome] += 1

        # Infer project type from cwd
        if session.cwd:
            if "test" in session.cwd.lower():
                session_char["project_types"]["testing"] += 1
            elif "api" in session.cwd.lower() or "backend" in session.cwd.lower():
                session_char["project_types"]["backend"] += 1
            elif "web" in session.cwd.lower() or "frontend" in session.cwd.lower():
                session_char["project_types"]["frontend"] += 1
            else:
                session_char["project_types"]["general"] += 1

        session_char["complexity_scores"].append({
            "session_id": session_id[:8],
            "score": round(complexity, 1),
            "outcome": outcome
        })

    # Sort by complexity
    session_char["complexity_scores"].sort(key=lambda x: -x["score"])
    session_char["most_complex"] = session_char["complexity_scores"][:5]
    session_char["least_complex"] = session_char["complexity_scores"][-5:]
    session_char["avg_complexity"] = sum(s["score"] for s in session_char["complexity_scores"]) / len(session_char["complexity_scores"]) if session_char["complexity_scores"] else 0
    session_char["project_types"] = dict(session_char["project_types"])
    del session_char["complexity_scores"]  # Keep only summary

    analytics["session_characterization"] = session_char

    # =========================================================================
    # PHASE 3: ACTIONABLE INSIGHTS
    # =========================================================================

    # 3.1 Optimization Opportunities
    optimization = {
        "cacheable_patterns": [],
        "avoidable_roundtrips": 0,
        "inefficient_sequences": [],
        "context_waste": 0
    }

    # Find repeated Read operations on same files (cacheable)
    read_files = defaultdict(int)
    for te in data.tool_executions:
        if te.tool_name == "Read" and te.input_params.get("file_path"):
            read_files[te.input_params["file_path"]] += 1

    # Files read more than 3 times = cacheable
    cacheable = [(f, c) for f, c in read_files.items() if c > 3]
    optimization["cacheable_patterns"] = [
        {"file": f.split("/")[-1], "reads": c, "savings": c - 1}
        for f, c in sorted(cacheable, key=lambda x: -x[1])[:10]
    ]
    optimization["total_cacheable_reads"] = sum(c - 1 for _, c in cacheable)

    # Avoidable roundtrips: Glob followed by Read of each result
    glob_then_read = tool_eff.get("top_sequences", {}).get("Glob -> Read", 0)
    optimization["avoidable_roundtrips"] = glob_then_read

    # Inefficient sequences: Edit followed by immediate Edit (could batch)
    edit_edit = tool_eff.get("top_sequences", {}).get("Edit -> Edit", 0)
    optimization["inefficient_sequences"].append({
        "pattern": "Edit -> Edit (batch opportunity)",
        "count": edit_edit
    })

    # Context waste: estimate from summaries (each summary = context overflow)
    optimization["context_waste_events"] = len(data.summaries)

    analytics["optimization"] = optimization

    # 3.2 User Experience
    ux = {
        "friction_points": [],
        "common_failures": defaultdict(int),
        "recovery_times": [],
        "session_health": {"healthy": 0, "warning": 0, "poor": 0}
    }

    # Friction points: sessions with high error rates or many retries
    for session_id, session in data.sessions.items():
        session_errors = [e for e in data.errors if e.session_id == session_id]
        error_rate = len(session_errors) / session.turns if session.turns else 0

        if error_rate > 0.1:  # More than 10% of turns have errors
            ux["friction_points"].append({
                "session_id": session_id[:8],
                "error_rate": round(error_rate * 100, 1),
                "errors": len(session_errors)
            })

        # Session health classification
        if len(session_errors) == 0 and session.dead_end_count == 0:
            ux["session_health"]["healthy"] += 1
        elif len(session_errors) <= 2 and session.dead_end_count <= 1:
            ux["session_health"]["warning"] += 1
        else:
            ux["session_health"]["poor"] += 1

    # Common failure modes from errors
    for err in data.errors:
        if err.status_code:
            ux["common_failures"][f"HTTP {err.status_code}"] += 1
        elif err.error_message:
            # Categorize error messages
            msg = err.error_message.lower()
            if "timeout" in msg:
                ux["common_failures"]["timeout"] += 1
            elif "rate" in msg or "limit" in msg:
                ux["common_failures"]["rate_limit"] += 1
            elif "permission" in msg or "denied" in msg:
                ux["common_failures"]["permission"] += 1
            else:
                ux["common_failures"]["other"] += 1

    ux["common_failures"] = dict(ux["common_failures"])
    ux["friction_points"] = sorted(ux["friction_points"], key=lambda x: -x["error_rate"])[:10]

    analytics["user_experience"] = ux

    # 3.3 Predictive Signals
    predictive = {
        "success_indicators": [],
        "failure_precursors": [],
        "compaction_signals": [],
        "thinking_recommendations": []
    }

    # Success indicators: patterns in productive sessions
    productive_sessions = [s for s in data.sessions.values()
                          if session_char["outcome_classification"]["productive"] > 0]

    # Analyze what productive sessions have in common
    if productive_sessions:
        avg_tools_productive = sum(s.tool_calls for s in productive_sessions) / len(productive_sessions)
        avg_depth_productive = sum(s.max_conversation_depth for s in productive_sessions) / len(productive_sessions)
        predictive["success_indicators"].append({
            "indicator": "tool_call_rate",
            "threshold": f"< {avg_tools_productive * 1.5:.0f} per session",
            "description": "Sessions with moderate tool usage tend to be productive"
        })

    # Failure precursors: patterns before errors
    for err in data.errors:
        # Look for thinking blocks just before error
        error_time = err.timestamp
        recent_thinking = [tb for tb in data.thinking_blocks
                          if tb.session_id == err.session_id
                          and tb.timestamp and error_time
                          and tb.timestamp < error_time]
        if recent_thinking:
            last_thinking = max(recent_thinking, key=lambda x: x.timestamp)
            if last_thinking.char_count > 1000:
                predictive["failure_precursors"].append({
                    "pattern": "extended_thinking_before_error",
                    "thinking_chars": last_thinking.char_count
                })

    # Compaction signals: when to suggest context summarization
    deep_sessions = [s for s in data.sessions.values() if s.max_conversation_depth > 100]
    if deep_sessions:
        predictive["compaction_signals"].append({
            "trigger": "depth > 100 messages",
            "sessions_affected": len(deep_sessions),
            "recommendation": "Suggest context compaction"
        })

    # High token sessions
    high_token_sessions = [s for s in data.sessions.values()
                          if s.total_input_tokens + s.total_output_tokens > 100000]
    if high_token_sessions:
        predictive["compaction_signals"].append({
            "trigger": "tokens > 100k",
            "sessions_affected": len(high_token_sessions),
            "recommendation": "Consider session reset or summary"
        })

    analytics["predictive"] = predictive

    return analytics


def print_report(data: ExtractedData, analytics: dict):
    """Print human-readable report."""
    print("=" * 70)
    print("ENHANCED LOG EXTRACTION REPORT")
    print("=" * 70)

    # Overview
    print(f"\n{'='*70}")
    print("OVERVIEW")
    print("=" * 70)
    ov = analytics["overview"]
    print(f"  Sessions:          {ov['total_sessions']:,}")
    print(f"  Turns:             {ov['total_turns']:,}")
    print(f"  Thinking blocks:   {ov['total_thinking_blocks']:,}")
    print(f"  Tool executions:   {ov['total_tool_executions']:,}")
    print(f"  Errors:            {ov['total_errors']:,}")
    print(f"  Progress events:   {ov['total_progress_events']:,}")
    print(f"  Summaries:         {ov['total_summaries']:,}")

    # Tokens
    print(f"\n{'='*70}")
    print("TOKEN USAGE")
    print("=" * 70)
    tok = analytics["tokens"]
    print(f"  Input tokens:      {tok['total_input']:,}")
    print(f"  Output tokens:     {tok['total_output']:,}")
    print(f"  Cache read:        {tok['total_cache_read']:,}")
    print(f"  Cache write:       {tok['total_cache_write']:,}")

    total_tokens = tok['total_input'] + tok['total_output']
    cache_hit_rate = tok['total_cache_read'] / tok['total_input'] * 100 if tok['total_input'] else 0
    print(f"\n  Total tokens:      {total_tokens:,}")
    print(f"  Cache hit rate:    {cache_hit_rate:.1f}%")

    # Thinking
    if analytics.get("thinking"):
        print(f"\n{'='*70}")
        print("THINKING ANALYSIS")
        print("=" * 70)
        th = analytics["thinking"]
        print(f"  Total characters:  {th['total_chars']:,}")
        print(f"  Total words:       {th['total_words']:,}")
        print(f"  Avg chars/block:   {th['avg_chars_per_block']:,}")
        print(f"  Avg words/block:   {th['avg_words_per_block']:,}")

        print(f"\n  Thinking by following action:")
        for action, stats in sorted(th.get('by_following_action', {}).items(),
                                     key=lambda x: -x[1]['count']):
            print(f"    {action}: {stats['count']} blocks, avg {stats['avg_chars']} chars")

    # Tool performance
    if analytics.get("tool_performance"):
        print(f"\n{'='*70}")
        print("TOOL PERFORMANCE (timing available)")
        print("=" * 70)
        for tool, perf in sorted(analytics["tool_performance"].items(),
                                  key=lambda x: -x[1]['total_ms']):
            print(f"\n  {tool}:")
            print(f"    Count:     {perf['count']}")
            print(f"    Avg:       {perf['avg_ms']:.0f}ms")
            print(f"    Min/Max:   {perf['min_ms']:.0f}ms / {perf['max_ms']:.0f}ms")
            print(f"    Total:     {perf['total_ms']/1000:.1f}s")

    # Turn timing
    if analytics.get("turn_timing"):
        print(f"\n{'='*70}")
        print("TURN TIMING")
        print("=" * 70)
        tt = analytics["turn_timing"]
        print(f"  Total turns:       {tt['total_turns']:,}")
        print(f"  Total time:        {tt['total_time_minutes']:.1f} minutes")
        print(f"  Avg turn:          {tt['avg_turn_ms']/1000:.1f}s")
        print(f"  Median turn:       {tt['median_turn_ms']/1000:.1f}s")
        print(f"  Min/Max:           {tt['min_turn_ms']/1000:.1f}s / {tt['max_turn_ms']/1000:.1f}s")

        if tt.get("distribution"):
            print(f"\n  Distribution:")
            for bucket, count in tt["distribution"].items():
                pct = count / tt['total_turns'] * 100 if tt['total_turns'] else 0
                bar = "#" * int(pct / 2)
                print(f"    {bucket:>8}: {count:4} ({pct:5.1f}%) {bar}")

    # Tool usage
    if analytics.get("tool_usage"):
        print(f"\n{'='*70}")
        print("TOOL USAGE & ERROR RATES")
        print("=" * 70)
        for tool, usage in sorted(analytics["tool_usage"].items(),
                                   key=lambda x: -x[1]['count']):
            err_pct = usage['error_rate'] * 100
            bytes_str = f", {usage['total_bytes']:,}B" if usage['total_bytes'] else ""
            print(f"  {tool}: {usage['count']} calls, {usage['errors']} errors ({err_pct:.1f}%){bytes_str}")

    # Errors
    if analytics.get("errors", {}).get("total"):
        print(f"\n{'='*70}")
        print("ERROR ANALYSIS")
        print("=" * 70)
        err = analytics["errors"]
        print(f"  Total errors:    {err['total']}")
        print(f"  Avg retries:     {err['avg_retries']:.1f}")
        if err.get("by_type"):
            print(f"\n  By type:")
            for etype, count in sorted(err["by_type"].items(), key=lambda x: -x[1]):
                print(f"    {etype}: {count}")

    # Agents
    if analytics.get("agents", {}).get("unique_agents"):
        print(f"\n{'='*70}")
        print("MULTI-AGENT ANALYSIS")
        print("=" * 70)
        ag = analytics["agents"]
        print(f"  Unique agents:       {ag['unique_agents']}")
        print(f"  Sessions w/ agents:  {ag['sessions_with_agents']}")

    # Versions
    if analytics.get("versions"):
        print(f"\n{'='*70}")
        print("CLAUDE CODE VERSIONS")
        print("=" * 70)
        for version, count in sorted(analytics["versions"].items(), key=lambda x: -x[1]):
            print(f"  {version}: {count} sessions")

    # Phase 1: Conversation Threading
    if analytics.get("threading"):
        print(f"\n{'='*70}")
        print("CONVERSATION THREADING")
        print("=" * 70)
        th = analytics["threading"]
        print(f"  Total messages:        {th['total_messages']:,}")
        print(f"  Avg conversation depth: {th['avg_depth']:.1f}")
        print(f"  Max depth:             {th['max_depth']}")
        print(f"  Total branches:        {th['total_branches']}")
        print(f"  Dead ends:             {th['total_dead_ends']}")
        print(f"  Sessions w/ branches:  {th['sessions_with_branches']}")

    # Phase 1: File Snapshots
    if analytics.get("file_snapshots"):
        print(f"\n{'='*70}")
        print("FILE HISTORY SNAPSHOTS")
        print("=" * 70)
        fs = analytics["file_snapshots"]
        print(f"  Total snapshots:       {fs['total_snapshots']:,}")
        print(f"  Unique files tracked:  {fs['unique_files_tracked']:,}")
        print(f"  Snapshot updates:      {fs['updates_vs_new']}")
        if fs.get("top_modified_files"):
            print(f"\n  Most modified files:")
            for path, count in list(fs["top_modified_files"].items())[:5]:
                short_path = path.split('/')[-1] if '/' in path else path
                print(f"    {short_path}: {count} snapshots")

    # Phase 1: Queue Operations
    if analytics.get("queue_operations"):
        print(f"\n{'='*70}")
        print("QUEUE OPERATIONS")
        print("=" * 70)
        qo = analytics["queue_operations"]
        print(f"  Total operations:      {qo['total']:,}")
        for op, count in sorted(qo.get("by_operation", {}).items(), key=lambda x: -x[1]):
            print(f"    {op}: {count}")

    # Phase 1: Thinking Metadata
    if analytics.get("thinking_metadata"):
        print(f"\n{'='*70}")
        print("THINKING METADATA")
        print("=" * 70)
        tm = analytics["thinking_metadata"]
        print(f"  Total entries:         {tm['total_entries']:,}")
        print(f"  Disabled count:        {tm['disabled_count']}")
        if tm.get("by_level"):
            print(f"\n  By level:")
            for level, count in sorted(tm["by_level"].items(), key=lambda x: -x[1]):
                print(f"    {level}: {count}")
        if tm.get("by_trigger"):
            print(f"\n  By trigger:")
            for trigger, count in sorted(tm["by_trigger"].items(), key=lambda x: -x[1]):
                print(f"    {trigger}: {count}")

    # Phase 1: Todos
    if analytics.get("todos"):
        print(f"\n{'='*70}")
        print("TODO TRACKING")
        print("=" * 70)
        td = analytics["todos"]
        print(f"  Total todos:           {td['total']:,}")
        print(f"  Completion rate:       {td['completion_rate']:.1f}%")
        if td.get("by_status"):
            print(f"\n  By status:")
            for status, count in sorted(td["by_status"].items(), key=lambda x: -x[1]):
                print(f"    {status}: {count}")

    # Phase 1: User Context
    if analytics.get("user_context"):
        print(f"\n{'='*70}")
        print("USER CONTEXT")
        print("=" * 70)
        uc = analytics["user_context"]
        if uc.get("permission_modes"):
            print(f"  Permission modes:")
            for mode, count in sorted(uc["permission_modes"].items(), key=lambda x: -x[1]):
                print(f"    {mode}: {count}")
        if uc.get("user_types"):
            print(f"\n  User types:")
            for utype, count in sorted(uc["user_types"].items(), key=lambda x: -x[1]):
                print(f"    {utype}: {count}")

    # Phase 1: API Requests
    if analytics.get("api_requests"):
        print(f"\n{'='*70}")
        print("API REQUEST TRACKING")
        print("=" * 70)
        ar = analytics["api_requests"]
        print(f"  Total requests:        {ar['total']:,}")
        print(f"  Unique request IDs:    {ar['unique_request_ids']:,}")
        print(f"  Error requests:        {ar['error_requests']}")
        print(f"  Error rate:            {ar['error_rate']:.1f}%")
        if ar.get("by_model"):
            print(f"\n  By model:")
            for model, count in sorted(ar["by_model"].items(), key=lambda x: -x[1]):
                print(f"    {model}: {count}")
        if ar.get("by_stop_reason"):
            print(f"\n  By stop reason:")
            for reason, count in sorted(ar["by_stop_reason"].items(), key=lambda x: -x[1]):
                print(f"    {reason}: {count}")

    # =========================================================================
    # PHASE 2: VALUE EXTRACTION ANALYTICS
    # =========================================================================

    # 2.1 Efficiency Metrics
    if analytics.get("efficiency"):
        print(f"\n{'='*70}")
        print("EFFICIENCY METRICS")
        print("=" * 70)
        eff = analytics["efficiency"]
        print(f"  Avg tokens per tool:   {eff.get('avg_tokens_per_tool', 0):.0f}")
        print(f"  Avg cache rate:        {eff.get('avg_cache_rate', 0):.1f}%")
        print(f"  Avg time per tool:     {eff.get('avg_time_per_tool_ms', 0):.0f}ms")

        if eff.get("most_token_heavy"):
            print(f"\n  Most token-heavy sessions:")
            for s in eff["most_token_heavy"][:3]:
                print(f"    {s['session_id']}: {s['tokens_per_tool']} tokens/tool, {s['tool_calls']} calls")

        if eff.get("most_efficient"):
            print(f"\n  Most efficient sessions:")
            for s in eff["most_efficient"][:3]:
                print(f"    {s['session_id']}: {s['tokens_per_tool']} tokens/tool, {s['tool_calls']} calls")

    # 2.2 Error Intelligence
    if analytics.get("error_intelligence"):
        print(f"\n{'='*70}")
        print("ERROR INTELLIGENCE")
        print("=" * 70)
        ei = analytics["error_intelligence"]
        print(f"  Sessions with errors:  {len(ei.get('error_sessions', []))}")
        print(f"  Recovery rate:         {ei.get('recovery_rate', 0):.1f}%")

        if ei.get("by_hour"):
            print(f"\n  Errors by hour (top 5):")
            for hour, count in sorted(ei["by_hour"].items(), key=lambda x: -x[1])[:5]:
                print(f"    {hour}:00 - {count} errors")

        if ei.get("by_version"):
            print(f"\n  Errors by version:")
            for version, count in sorted(ei["by_version"].items(), key=lambda x: -x[1])[:5]:
                print(f"    {version}: {count}")

    # 2.3 Conversation Flow
    if analytics.get("conversation_flow"):
        print(f"\n{'='*70}")
        print("CONVERSATION FLOW ANALYSIS")
        print("=" * 70)
        flow = analytics["conversation_flow"]
        print(f"  Sidechain sessions:    {len(flow.get('sidechain_sessions', []))}")
        print(f"  Avg depth at summary:  {flow.get('avg_depth_at_summary', 0):.0f} messages")

        if flow.get("depth_distribution"):
            print(f"\n  Session depth distribution:")
            for depth, count in flow["depth_distribution"].items():
                print(f"    {depth}: {count} sessions")

    # 2.4 Tool Effectiveness
    if analytics.get("tool_effectiveness"):
        print(f"\n{'='*70}")
        print("TOOL EFFECTIVENESS")
        print("=" * 70)
        te = analytics["tool_effectiveness"]
        print(f"  Total redundant calls: {te.get('total_redundant', 0)}")

        if te.get("top_sequences"):
            print(f"\n  Common tool sequences:")
            for seq, count in list(te["top_sequences"].items())[:10]:
                print(f"    {seq}: {count}")

        if te.get("redundant_calls"):
            print(f"\n  Redundant calls by tool:")
            for tool, count in sorted(te["redundant_calls"].items(), key=lambda x: -x[1])[:5]:
                print(f"    {tool}: {count} extra calls")

        if te.get("latency_by_tool"):
            print(f"\n  Latency percentiles (p50/p90/p99):")
            for tool, lat in sorted(te["latency_by_tool"].items(), key=lambda x: -x[1]['p50'])[:5]:
                print(f"    {tool}: {lat['p50']:.0f}ms / {lat['p90']:.0f}ms / {lat['p99']:.0f}ms")

    # 2.5 Thinking Efficiency
    if analytics.get("thinking_efficiency"):
        print(f"\n{'='*70}")
        print("THINKING EFFICIENCY")
        print("=" * 70)
        th = analytics["thinking_efficiency"]
        print(f"  Wasted thinking:       {th.get('wasted_thinking', 0)} blocks ({th.get('wasted_thinking_pct', 0):.1f}%)")

        if th.get("avg_by_outcome"):
            print(f"\n  Avg thinking by outcome:")
            for outcome, avg in sorted(th["avg_by_outcome"].items(), key=lambda x: -x[1])[:5]:
                print(f"    {outcome}: {avg} chars")

    # 2.6 Session Characterization
    if analytics.get("session_characterization"):
        print(f"\n{'='*70}")
        print("SESSION CHARACTERIZATION")
        print("=" * 70)
        sc = analytics["session_characterization"]
        print(f"  Avg complexity score:  {sc.get('avg_complexity', 0):.1f}")

        if sc.get("outcome_classification"):
            print(f"\n  Outcome classification:")
            for outcome, count in sc["outcome_classification"].items():
                print(f"    {outcome}: {count} sessions")

        if sc.get("project_types"):
            print(f"\n  Project types:")
            for ptype, count in sorted(sc["project_types"].items(), key=lambda x: -x[1]):
                print(f"    {ptype}: {count}")

        if sc.get("most_complex"):
            print(f"\n  Most complex sessions:")
            for s in sc["most_complex"][:3]:
                print(f"    {s['session_id']}: score {s['score']}, {s['outcome']}")

    # =========================================================================
    # PHASE 3: ACTIONABLE INSIGHTS
    # =========================================================================

    # 3.1 Optimization Opportunities
    if analytics.get("optimization"):
        print(f"\n{'='*70}")
        print("OPTIMIZATION OPPORTUNITIES")
        print("=" * 70)
        opt = analytics["optimization"]
        print(f"  Cacheable read savings: {opt.get('total_cacheable_reads', 0)} calls")
        print(f"  Avoidable roundtrips:   {opt.get('avoidable_roundtrips', 0)}")
        print(f"  Context waste events:   {opt.get('context_waste_events', 0)}")

        if opt.get("cacheable_patterns"):
            print(f"\n  Top cacheable files:")
            for cp in opt["cacheable_patterns"][:5]:
                print(f"    {cp['file']}: {cp['reads']} reads ({cp['savings']} cacheable)")

        if opt.get("inefficient_sequences"):
            print(f"\n  Inefficient patterns:")
            for seq in opt["inefficient_sequences"]:
                print(f"    {seq['pattern']}: {seq['count']} occurrences")

    # 3.2 User Experience
    if analytics.get("user_experience"):
        print(f"\n{'='*70}")
        print("USER EXPERIENCE ANALYSIS")
        print("=" * 70)
        ux = analytics["user_experience"]

        if ux.get("session_health"):
            print(f"  Session health:")
            for health, count in ux["session_health"].items():
                print(f"    {health}: {count} sessions")

        if ux.get("common_failures"):
            print(f"\n  Common failure modes:")
            for failure, count in sorted(ux["common_failures"].items(), key=lambda x: -x[1]):
                print(f"    {failure}: {count}")

        if ux.get("friction_points"):
            print(f"\n  High-friction sessions:")
            for fp in ux["friction_points"][:5]:
                print(f"    {fp['session_id']}: {fp['error_rate']}% error rate")

    # 3.3 Predictive Signals
    if analytics.get("predictive"):
        print(f"\n{'='*70}")
        print("PREDICTIVE SIGNALS")
        print("=" * 70)
        pred = analytics["predictive"]

        if pred.get("success_indicators"):
            print(f"  Success indicators:")
            for si in pred["success_indicators"]:
                print(f"    {si['indicator']}: {si['threshold']}")
                print(f"      {si['description']}")

        if pred.get("compaction_signals"):
            print(f"\n  Compaction signals:")
            for cs in pred["compaction_signals"]:
                print(f"    {cs['trigger']}: {cs['sessions_affected']} sessions")
                print(f"      -> {cs['recommendation']}")

    # Sample insights
    print(f"\n{'='*70}")
    print("INSIGHTS")
    print("=" * 70)

    # Thinking efficiency
    if analytics.get("thinking") and analytics.get("tool_usage"):
        total_thinking_chars = analytics["thinking"]["total_chars"]
        total_tool_calls = sum(u["count"] for u in analytics["tool_usage"].values())
        if total_tool_calls:
            chars_per_action = total_thinking_chars / total_tool_calls
            print(f"\n  Thinking efficiency:")
            print(f"    {chars_per_action:.0f} chars of reasoning per tool call")

    # Slowest tools
    if analytics.get("tool_performance"):
        slowest = sorted(analytics["tool_performance"].items(),
                        key=lambda x: -x[1]['avg_ms'])[:3]
        print(f"\n  Slowest tools (avg):")
        for tool, perf in slowest:
            print(f"    {tool}: {perf['avg_ms']:.0f}ms")

    # Most error-prone
    if analytics.get("tool_usage"):
        error_prone = [(t, u) for t, u in analytics["tool_usage"].items()
                       if u['errors'] > 0]
        if error_prone:
            error_prone.sort(key=lambda x: -x[1]['error_rate'])
            print(f"\n  Most error-prone tools:")
            for tool, usage in error_prone[:3]:
                print(f"    {tool}: {usage['error_rate']*100:.1f}% error rate")

    print("\n" + "=" * 70)


def find_all_sessions(claude_dir: Path = None) -> list:
    """Find all session JSONL files."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude" / "projects"

    sessions = []
    if not claude_dir.exists():
        return sessions

    for project_dir in claude_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            sessions.append(jsonl_file)

    return sessions


def to_serializable(obj):
    """Convert dataclasses and other objects to JSON-serializable format."""
    if hasattr(obj, '__dataclass_fields__'):
        return asdict(obj)
    elif isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, defaultdict):
        return dict(obj)
    return obj


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enhanced extraction from Claude Code logs")
    parser.add_argument("file", nargs="?", type=Path, help="Specific JSONL file to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--export", type=Path, help="Export full data to JSON file")
    parser.add_argument("--report", action="store_true", help="Print human-readable report (default)")
    args = parser.parse_args()

    if args.file:
        sessions = [args.file]
    else:
        sessions = find_all_sessions()

    if not sessions:
        print("No sessions found.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting from {len(sessions)} session files...", file=sys.stderr)

    # Extract from all sessions
    all_data = []
    for session_path in sessions:
        try:
            data = extract_from_session(session_path)
            all_data.append(data)
        except Exception as e:
            print(f"Warning: Failed to extract {session_path}: {e}", file=sys.stderr)

    # Merge all data
    merged = merge_extracted_data(all_data)

    # Compute conversation trees (updates session metadata)
    trees = compute_conversation_trees(merged)
    merged.conversation_trees = trees

    # Compute analytics
    analytics = compute_analytics(merged)

    # Output
    if args.export:
        export_data = {
            "analytics": analytics,
            "sessions": {k: to_serializable(v) for k, v in merged.sessions.items()},
            "thinking_blocks": [to_serializable(tb) for tb in merged.thinking_blocks],
            "tool_executions": [to_serializable(te) for te in merged.tool_executions],
            "errors": [to_serializable(e) for e in merged.errors],
            "progress_events": [to_serializable(pe) for pe in merged.progress_events],
            "summaries": [to_serializable(s) for s in merged.summaries],
            "turn_durations": [to_serializable(td) for td in merged.turn_durations],
            "tool_timing": dict(merged.tool_timing),
            # Phase 1 additions
            "message_nodes": [to_serializable(mn) for mn in merged.message_nodes],
            "file_snapshots": [to_serializable(fs) for fs in merged.file_snapshots],
            "queue_operations": [to_serializable(qo) for qo in merged.queue_operations],
            "thinking_metadata": [to_serializable(tm) for tm in merged.thinking_metadata],
            "todos": [to_serializable(td) for td in merged.todos],
            "api_requests": [to_serializable(ar) for ar in merged.api_requests],
            "conversation_trees": merged.conversation_trees
        }
        with open(args.export, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        print(f"Exported to {args.export}", file=sys.stderr)

    if args.json:
        print(json.dumps(analytics, indent=2, default=str))
    else:
        print_report(merged, analytics)


if __name__ == "__main__":
    main()
