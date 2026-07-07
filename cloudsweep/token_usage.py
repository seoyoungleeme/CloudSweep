"""Best-effort Claude token usage accounting for one CloudSweep completion.

The deterministic graph/report renderer does not call an LLM API itself. LLM
work happens in the Claude Code session that completes the surrounding workflow:
complex Skill analysis, public-pricing model lookup/writeup, AI review, and
report polish. Those stages are one CloudSweep completion, so usage is recovered
as a single window from this machine's Claude Code transcript rather than split
into separate reports.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

MODEL_ID = "claude-sonnet-5"

# Standard (non-intro) Sonnet 5 list pricing, USD per million tokens.
_INPUT_PRICE_PER_MTOK = 3.00
_OUTPUT_PRICE_PER_MTOK = 15.00
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.1

_START_MARKER_NAME = ".token_usage_start.json"
_SNAPSHOT_NAME = "token_usage.json"

# A run that never reaches final report completion (abandoned, dry-run only, etc.) would
# otherwise keep the same start marker forever, silently widening the
# measured window to include unrelated work done far later. Treat a marker
# older than this as stale and start a fresh window instead.
_MAX_MARKER_AGE_HOURS = 3

_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def _project_slug(cwd: Path) -> str:
    return re.sub(r"[:\\/]", "-", str(cwd))


def _project_dir(cwd: Path | None = None) -> Path | None:
    cwd = (cwd or Path.cwd()).resolve()
    candidate = Path.home() / ".claude" / "projects" / _project_slug(cwd)
    return candidate if candidate.exists() else None


def _marker_path(result_dir: Path) -> Path:
    # Lives under result/.machine/ alongside the other machine-only working
    # files (cloudsweep_graph_state.json, skill/pricing requests) -- never a
    # human-facing artifact.
    return Path(result_dir) / ".machine" / _START_MARKER_NAME


def _snapshot_path(result_dir: Path) -> Path:
    return Path(result_dir) / ".machine" / _SNAPSHOT_NAME


def record_start_marker(result_dir: Path, run_id: str | None = None) -> None:
    """Record when this run's analysis began, if not already recorded.

    Left untouched across repeated LangGraph passes within the same overall
    run (evidence -> skill/pricing requests -> Claude fills them in -> rerun
    -> AI review -> report polish -> final graph render) so the eventual token
    count covers that whole run -- not just the last LangGraph invocation. The
    final graph render clears the marker when a run completes so the *next* run
    starts a fresh window; the staleness check here is a safety net for runs
    that never reach completion.
    """
    marker = _marker_path(result_dir)
    if marker.exists():
        existing = _read_marker(result_dir)
        existing_start = _marker_start_time(existing)
        existing_run_id = existing.get("run_id") if existing else None
        if existing_start is not None:
            age_hours = (datetime.now(timezone.utc) - existing_start).total_seconds() / 3600
            same_run = not run_id or not existing_run_id or existing_run_id == run_id
            if age_hours < _MAX_MARKER_AGE_HOURS and same_run:
                return
    marker.parent.mkdir(parents=True, exist_ok=True)
    start_time = datetime.now(timezone.utc).isoformat()
    marker.write_text(
        json.dumps(
            {
                "start_time": start_time,
                "run_id": run_id,
                "window_id": uuid4().hex,
            }
        ),
        encoding="utf-8",
    )


def clear_start_marker(result_dir: Path) -> None:
    """Close out the current run's measurement window.

    Called once a run's final report has been written, so the next invocation
    for this scenario starts counting from a fresh marker instead of reusing
    this run's (now-stale) start time.
    """
    _marker_path(result_dir).unlink(missing_ok=True)


def write_usage_snapshot(result_dir: Path, usage: dict[str, Any], *, run_id: str | None = None) -> None:
    """Persist the measured final usage so rerenders do not erase it."""
    if not usage.get("measured"):
        return
    snapshot = dict(usage)
    snapshot.pop("from_snapshot", None)
    snapshot.pop("snapshot_reason", None)
    if run_id and not snapshot.get("run_id"):
        snapshot["run_id"] = run_id
    snapshot["snapshot_saved_at"] = datetime.now(timezone.utc).isoformat()
    path = _snapshot_path(result_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_usage_snapshot(
    result_dir: Path,
    reason: str,
    *,
    run_id: str | None = None,
    active_marker: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    path = _snapshot_path(result_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("measured"):
        return None
    if run_id and data.get("run_id") != run_id:
        return None
    if active_marker is not None:
        marker_window = active_marker.get("window_id")
        marker_start = active_marker.get("start_time")
        same_window = marker_window and data.get("window_id") == marker_window
        same_start = marker_start and data.get("start_time") == marker_start
        if not same_window and not same_start:
            return None
    snapshot = dict(data)
    snapshot["from_snapshot"] = True
    snapshot["snapshot_reason"] = reason
    return snapshot


def _read_marker(result_dir: Path) -> dict[str, Any] | None:
    marker = _marker_path(result_dir)
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _marker_start_time(marker: dict[str, Any] | None) -> datetime | None:
    if not marker:
        return None
    try:
        return datetime.fromisoformat(str(marker["start_time"]))
    except (KeyError, ValueError):
        return None


def _read_start_time(result_dir: Path) -> datetime | None:
    return _marker_start_time(_read_marker(result_dir))


def _candidate_transcripts(project_dir: Path, start_time: datetime) -> list[Path]:
    candidates = []
    for path in project_dir.glob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime >= start_time:
            candidates.append(path)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates


def _sum_usage(transcript: Path, start_time: datetime) -> dict[str, int]:
    totals = {key: 0 for key in _USAGE_KEYS}
    totals["message_count"] = 0
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return totals
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        timestamp = entry.get("timestamp")
        if timestamp:
            try:
                ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except ValueError:
                ts = None
            if ts is not None and ts < start_time:
                continue
        for key in _USAGE_KEYS:
            totals[key] += int(usage.get(key, 0) or 0)
        totals["message_count"] += 1
    return totals


def _estimate_cost_usd(totals: dict[str, int]) -> float:
    cost = (
        totals["input_tokens"] * _INPUT_PRICE_PER_MTOK
        + totals["output_tokens"] * _OUTPUT_PRICE_PER_MTOK
        + totals["cache_creation_input_tokens"] * _INPUT_PRICE_PER_MTOK * _CACHE_WRITE_MULTIPLIER
        + totals["cache_read_input_tokens"] * _INPUT_PRICE_PER_MTOK * _CACHE_READ_MULTIPLIER
    ) / 1_000_000
    return round(cost, 4)


def compute_usage(result_dir: Path, *, cwd: Path | None = None, run_id: str | None = None) -> dict[str, Any]:
    """Recover Claude token usage for one sample's analysis window.

    Sums assistant-turn usage from this machine's Claude Code session
    transcript between the sample's recorded start marker and now. Covers
    only the primary session transcript -- subagent transcripts (stored
    under ``<session>/subagents/``) are not included, so this undercounts
    when subagents did part of the analysis.
    """
    result_dir = Path(result_dir)
    marker = _read_marker(result_dir)
    start_time = _marker_start_time(marker)
    if start_time is None:
        snapshot = _load_usage_snapshot(result_dir, "no active start marker", run_id=run_id)
        if snapshot:
            return snapshot
        return {"measured": False, "reason": "no start marker recorded for this run"}

    project_dir = _project_dir(cwd)
    if project_dir is None:
        snapshot = _load_usage_snapshot(
            result_dir,
            "Claude Code session directory not found",
            run_id=run_id,
            active_marker=marker,
        )
        if snapshot:
            return snapshot
        return {"measured": False, "reason": "Claude Code session directory not found"}

    candidates = _candidate_transcripts(project_dir, start_time)
    if not candidates:
        snapshot = _load_usage_snapshot(
            result_dir,
            "no new transcript activity",
            run_id=run_id,
            active_marker=marker,
        )
        if snapshot:
            return snapshot
        return {"measured": False, "reason": "no session transcript activity since analysis started"}

    totals = {key: 0 for key in _USAGE_KEYS}
    totals["message_count"] = 0
    for transcript in candidates:
        partial = _sum_usage(transcript, start_time)
        for key in totals:
            totals[key] += partial[key]

    total_tokens = sum(totals[key] for key in _USAGE_KEYS)
    if total_tokens == 0:
        snapshot = _load_usage_snapshot(
            result_dir,
            "no token usage in current window",
            run_id=run_id,
            active_marker=marker,
        )
        if snapshot:
            return snapshot
    return {
        "measured": True,
        "model": MODEL_ID,
        "run_id": marker.get("run_id") or run_id,
        "window_id": marker.get("window_id"),
        "start_time": marker.get("start_time"),
        **totals,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _estimate_cost_usd(totals),
    }


def render_markdown(usage: dict[str, Any]) -> list[str]:
    """Render the usage dict as a report section's lines."""
    lines = ["## Token & Cost Usage", ""]
    if not usage.get("measured"):
        lines.append(f"Not measured ({usage.get('reason', 'unknown')}).")
        return lines
    lines.extend(
        [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Model | {usage['model']} |",
            f"| Input tokens | {usage['input_tokens']:,} |",
            f"| Output tokens | {usage['output_tokens']:,} |",
            f"| Cache write tokens | {usage['cache_creation_input_tokens']:,} |",
            f"| Cache read tokens | {usage['cache_read_input_tokens']:,} |",
            f"| Total tokens | {usage['total_tokens']:,} |",
            f"| Estimated cost (USD) | ${usage['estimated_cost_usd']:.4f} |",
            "",
        ]
    )
    if usage.get("from_snapshot"):
        lines.append(
            "_Persisted from the completed CloudSweep AI window because this rerender "
            f"had {usage.get('snapshot_reason', 'no new measurable activity')}. "
            "The total covers complex Skill work, AI review, and report polish from "
            "that completed window; deterministic Python graph rendering itself does "
            "not call an LLM and subagent-session token spend is excluded._"
        )
    else:
        lines.append(
            "_Recovered from this machine's Claude Code session transcript for the "
            "current CloudSweep completion window. This is a single total for complex "
            "Skill work, AI review, and report polish performed in that window "
            "(standard Sonnet 5 list pricing, $3/$15 per MTok); deterministic Python "
            "graph rendering itself does not call an LLM and subagent-session token "
            "spend is excluded._"
        )
    return lines
