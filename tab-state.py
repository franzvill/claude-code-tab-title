#!/usr/bin/env python3
"""tab-state.py — VS Code terminal tab title for Claude Code.

Title = the topic the user is discussing, derived from their own messages
only (Claude's responses are ignored). The topic is sticky across short
prompts ("ok", "do it", "fix it") so a quick follow-up doesn't clobber it;
prompts at or above MIN_TOPIC_LEN replace it. Length-only — no English-
specific ack/continuation word list.

Updates only on UserPromptSubmit. SessionStart writes a project-name
fallback so the tab shows something predictable before the first message.

Per-session state at /tmp/claude-tab-<session_id>:
  topic       — current sticky topic
  last_title  — last title we wrote (for dedup)

The prompt body is truncated to PROMPT_SLICE bytes before any processing
(big paste-ins or multi-page prompts don't need to be fully scanned).

Output: OSC title-change escape written directly to the parent claude
process's controlling tty. Hooks have no /dev/tty of their own (Claude
Code isolates them), so we walk the process tree to find a writable pty.
Stdout stays silent. Always exits 0.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

TITLE_MAX = 26
PROMPT_SLICE = 500
MIN_TOPIC_LEN = 10  # prompts shorter than this are treated as continuations
                    # and don't overwrite the topic. Length-only — no
                    # English-specific ack/continuation word list.


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


def trim(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > TITLE_MAX:
        cleaned = cleaned[: TITLE_MAX - 1].rstrip() + "…"
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


def is_continuation(prompt: str) -> bool:
    return len(prompt.strip()) < MIN_TOPIC_LEN


def fallback(payload: dict) -> str:
    cwd = payload.get("cwd") or os.getcwd()
    return Path(cwd).name or "Claude"


def find_terminal_device() -> str:
    try:
        with open("/dev/tty", "w") as f:
            pass
        return "/dev/tty"
    except Exception:
        pass
    pid = os.getppid()
    for _ in range(10):
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


def main() -> int:
    state = sys.argv[1] if len(sys.argv) > 1 else "idle"

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    session_id = str(payload.get("session_id") or "default")
    sp = state_path(session_id)
    persisted = load_state(sp)
    topic = persisted.get("topic") or ""

    if state == "working":
        prompt = (payload.get("prompt") or "")[:PROMPT_SLICE]
        candidate = first_line(prompt)
        if candidate:
            if not topic or not is_continuation(prompt):
                topic = candidate

    title = trim(topic) or trim(fallback(payload))

    if persisted.get("last_title") != title:
        write_title(title)
        persisted["last_title"] = title
    persisted["topic"] = topic
    save_state(sp, persisted)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
