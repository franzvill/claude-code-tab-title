# claude-code-tab-title

Terminal tab/window titles that show what each Claude Code session is working on, with a busy/idle marker. Works in VS Code's integrated terminal, iTerm2, Terminal.app, and any other terminal that honors standard OSC title sequences.

When you have multiple `claude` sessions running in different terminal tabs/windows, the titles all collapse to the binary name (`2.1.119`) or to a static shell label, so you can't tell at a glance which session is doing what. This wires up two hooks that render each tab/window's title as `<marker> <topic>`:

- `*` when you've just submitted (Claude is working) → flips at `UserPromptSubmit`
- `·` when Claude has finished its turn (idle) → flips at `Stop`

The topic is set once, from the first prompt of the session, and stays sticky until the session ends.

## What it looks like

**One session, over a single turn:**

```
· your-project            ← SessionStart writes a project-name fallback
* Refactor auth flow      ← after your first prompt: topic seeded, marker = busy
· Refactor auth flow      ← Claude finishes the turn → marker flips to idle
* Refactor auth flow      ← you reply "ok do that part" → marker flips back to busy
                            (topic stays — sticky from first prompt)
· Refactor auth flow      ← Claude finishes → idle again
```

**Four parallel sessions** (each line is a tab/window):

```
* Auth refactor           ← Claude working on this one right now
· Stripe webhook          ← idle, waiting for you to reply
* Migration runner        ← Claude working
· Tab title hook          ← idle
```

<img width="353" height="117" alt="image" src="https://github.com/user-attachments/assets/327604f1-e6d6-4ee3-bf0d-65c056ca7349" />

## Install

### Option A — via Claude Code plugin (recommended)

Two slash commands in any claude session:

```
/plugin marketplace add franzvill/claude-code-tab-title
/plugin install tab-title@claude-code-tab-title
```

That installs `tab-state.py` and registers all three hooks (`UserPromptSubmit`, `Stop`, `SessionStart`). Nothing else to configure — open a new claude tab and submit a prompt.

To update later: `/plugin marketplace update`. To uninstall: `/plugin uninstall tab-title@claude-code-tab-title`.

### Option B — manual install

If you'd rather not use the plugin system:

```bash
mkdir -p ~/.claude/hooks
curl -fsSL https://raw.githubusercontent.com/franzvill/claude-code-tab-title/main/plugins/tab-title/tab-state.py \
  -o ~/.claude/hooks/tab-state.py
chmod +x ~/.claude/hooks/tab-state.py
```

Then merge the hook entries into `~/.claude/settings.json` (don't replace existing hook arrays — append):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "~/.claude/hooks/tab-state.py working" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "~/.claude/hooks/tab-state.py idle" }] }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "~/.claude/hooks/tab-state.py idle" }] }
    ]
  }
}
```

Restart any running `claude` sessions for the new hooks to load.

## How it works

**On `SessionStart`** — writes `· <cwd basename>` as a fallback title so the tab shows something predictable before the first prompt.

**On `UserPromptSubmit`** — if no topic is in state yet, takes the first non-empty line of the prompt (sliced to first 500 bytes for safety on huge paste-ins), saves it as the topic, and writes `* <topic>`. If a topic is already set, just rewrites the title with the `*` marker — the topic itself doesn't change.

**On `Stop`** — rewrites the title with the `·` marker, keeping the existing topic.

**Why we walk the process tree to write OSC:** Claude Code spawns hooks with no controlling tty of their own (so hook stdout/stderr can't bleed into the conversation). Writing to `/dev/tty` from the hook silently fails. The script falls back to the parent process tree to find the parent claude's real pty (for example `/dev/ttys020` on macOS or `/dev/pts/1` on Linux) and writes there directly, walking up to 10 hops if the parent itself has no tty. On Linux it reads `/proc/<pid>/stat`; elsewhere it uses `ps -o tty=,ppid= -p $PPID`.

**State** is per-session at `/tmp/claude-tab-<session_id>` — JSON with `topic`, `marker_state`, and `last_title`. Dedup on `last_title` means hooks that compose an unchanged title don't re-emit OSC sequences.

## Caveats

- **Tested terminal families** include VS Code's integrated terminal, iTerm2, Terminal.app, and Linux terminals that expose the controlling TTY through `/proc/<pid>/stat`.
- **Tested in** VS Code's integrated terminal, iTerm2, and Terminal.app. Any terminal honoring standard OSC `\033]0;...\007` title sequences should work the same way.
- **Manual tab rename will be overwritten** by the next `UserPromptSubmit` or `Stop`. Disable the hook entries if you'd rather rename manually.
- **Existing hooks aren't clobbered** as long as you append rather than replace the JSON (manual install) or use the plugin (which adds hooks alongside any user-defined ones).

## Uninstall

**Option A**: `/plugin uninstall tab-title@claude-code-tab-title`.

**Option B**: `rm ~/.claude/hooks/tab-state.py` and remove the three hook entries from `~/.claude/settings.json`.

## License

[MIT](LICENSE)
