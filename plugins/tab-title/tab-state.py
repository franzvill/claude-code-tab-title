#!/usr/bin/env python3
"""tab-state.py — VS Code terminal tab title for Claude Code.

Title format: "<marker> <topic>" where:
  marker = "*" while Claude is working, "·" when idle.
  topic  = first substantive prompt of the session (sticky after that),
           or whatever has been set via --topic.

Modes:
  tab-state.py working
    UserPromptSubmit hook. If no topic is set yet, seeds it from the
    first non-empty line of the prompt. Writes "* <topic>".

  tab-state.py idle
    Stop / SessionStart hook. Writes "· <topic>". Falls back to the
    cwd basename when no topic is known yet.

  tab-state.py --topic "Refactor auth"
    Sets the topic explicitly for the current session and rewrites the
    title with the current marker. Use this from Claude itself (via a
    Bash call in your first response) to write a synthesized topic
    instead of the literal first-prompt line.

State per session at /tmp/claude-tab-<session_id>:
  topic        — sticky topic
  marker_state — "working" or "idle" — drives the prefix character
  last_title   — last full title we wrote (dedup)

Output: OSC title escape written directly to the parent claude
process's controlling pty (hooks have no /dev/tty of their own). Stdout
stays silent. Always exits 0.
"""

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

TITLE_MAX = 28
PROMPT_SLICE = 500
MAX_PROCESS_HOPS = 10
MARKER_WORKING = "*"
MARKER_IDLE = "·"


def state_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id) or "default"
    return Path(f"/tmp/claude-tab-{safe}")


def load_state(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_state(p: Path, s: dict) -> None:
    try:
        p.write_text(json.dumps(s))
    except Exception:
        pass


def trim_topic(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    body_max = TITLE_MAX - 2  # reserve "* "
    if len(cleaned) > body_max:
        cleaned = cleaned[: body_max - 1].rstrip() + "…"
    return cleaned


def first_line(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    if s.startswith("```"):
        rest = s[3:]
        end = rest.find("```")
        s = (rest[end + 3:] if end != -1 else rest).strip()
    return next((L.strip() for L in s.splitlines() if L.strip()), "")


def fallback(payload: dict) -> str:
    cwd = payload.get("cwd") or os.getcwd()
    return Path(cwd).name or "Claude"


def parse_linux_proc_stat(stat_text: str) -> tuple[int, int] | None:
    """Return (ppid, tty_nr) from Linux /proc/<pid>/stat text."""
    end_comm = stat_text.rfind(")")
    if end_comm == -1:
        return None
    fields = stat_text[end_comm + 2 :].split()
    # Remaining fields start at field 3: state, ppid, pgrp, session, tty_nr.
    if len(fields) < 5:
        return None
    try:
        return int(fields[1]), int(fields[4])
    except ValueError:
        return None


def linux_proc_info(pid: int) -> tuple[int, int] | None:
    try:
        return parse_linux_proc_stat(Path(f"/proc/{pid}/stat").read_text())
    except Exception:
        return None


def linux_tty_path(tty_nr: int, dev_root: Path = Path("/dev")) -> str:
    if tty_nr <= 0:
        return ""

    candidates = [dev_root / "pts"]
    candidates.extend(dev_root.glob("tty*"))

    for candidate in candidates:
        paths = candidate.iterdir() if candidate.is_dir() else [candidate]
        for path in paths:
            try:
                if os.stat(path).st_rdev == tty_nr and os.access(path, os.W_OK):
                    return str(path)
            except Exception:
                continue
    return ""


def find_terminal_device_linux(pid: int | None = None) -> str:
    pid = os.getppid() if pid is None else pid
    for _ in range(MAX_PROCESS_HOPS):
        if pid <= 1:
            break
        proc_info = linux_proc_info(pid)
        if not proc_info:
            break
        ppid, tty_nr = proc_info
        path = linux_tty_path(tty_nr)
        if path:
            return path
        pid = ppid
    return ""


def find_terminal_device_ps(pid: int | None = None) -> str:
    pid = os.getppid() if pid is None else pid
    for _ in range(MAX_PROCESS_HOPS):
        if pid <= 1:
            break
        try:
            r = subprocess.run(
                ["ps", "-o", "tty=,ppid=", "-p", str(pid)],
                capture_output=True, text=True, timeout=1,
            )
        except Exception:
            break
        parts = r.stdout.split()
        if len(parts) < 2:
            break
        tty_name, ppid_str = parts[0], parts[1]
        if tty_name and tty_name not in ("??", "?"):
            path = f"/dev/{tty_name}"
            if os.path.exists(path) and os.access(path, os.W_OK):
                return path
        pid = int(ppid_str) if ppid_str.isdigit() else 0
    return ""


def find_terminal_device() -> str:
    """Locate a writable tty for the parent claude pty.

    Hooks have no controlling tty (Claude Code isolates them so hook
    stdout/stderr don't bleed into the conversation), so /dev/tty
    typically fails. Walk the process tree until we find a process
    whose tty exists and is writable.
    """
    try:
        with open("/dev/tty", "w") as f:
            pass
        return "/dev/tty"
    except Exception:
        pass
    if platform.system() == "Linux":
        return find_terminal_device_linux()
    return find_terminal_device_ps()


def write_title(title: str) -> None:
    path = find_terminal_device()
    if not path:
        return
    try:
        with open(path, "w") as tty:
            tty.write(f"\x1b]0;{title}\x07")
            tty.flush()
    except Exception:
        pass


def find_session_id_from_process() -> str:
    """In --topic mode there's no stdin payload, so we have to find the
    session_id another way. Walk up the process tree; for each pid look
    for ~/.claude/sessions/<pid>.json which has the sessionId UUID."""
    pid = os.getppid()
    sessions_dir = Path.home() / ".claude" / "sessions"
    for _ in range(10):
        if pid <= 1:
            break
        sf = sessions_dir / f"{pid}.json"
        if sf.exists():
            try:
                data = json.loads(sf.read_text())
                sid = data.get("sessionId")
                if sid:
                    return sid
            except Exception:
                pass
        try:
            r = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True, text=True, timeout=1,
            )
        except Exception:
            break
        parent = r.stdout.strip()
        pid = int(parent) if parent.isdigit() else 0
    return ""


def parse_args(argv):
    """Returns (mode, topic_override)."""
    args = list(argv[1:])
    topic = None
    mode = "idle"
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--topic" and i + 1 < len(args):
            topic = args[i + 1]
            i += 2
            continue
        if a in ("working", "idle"):
            mode = a
        i += 1
    return mode, topic


def main() -> int:
    mode, topic_override = parse_args(sys.argv)

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = (
        str(payload.get("session_id") or "")
        or find_session_id_from_process()
        or "default"
    )
    sp = state_path(session_id)
    persisted = load_state(sp)

    topic = persisted.get("topic") or ""
    marker_state = persisted.get("marker_state") or "idle"

    if topic_override is not None:
        topic = topic_override
    elif mode == "working" and not topic:
        # First UserPromptSubmit: seed topic from the first line of the prompt.
        prompt = (payload.get("prompt") or "")[:PROMPT_SLICE]
        candidate = first_line(prompt)
        if candidate:
            topic = candidate

    if mode in ("working", "idle"):
        marker_state = mode

    if not topic:
        topic = fallback(payload)

    marker = MARKER_WORKING if marker_state == "working" else MARKER_IDLE
    body = trim_topic(topic)
    title = f"{marker} {body}".strip()

    if persisted.get("last_title") != title:
        write_title(title)
        persisted["last_title"] = title
    persisted["topic"] = topic
    persisted["marker_state"] = marker_state
    save_state(sp, persisted)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
