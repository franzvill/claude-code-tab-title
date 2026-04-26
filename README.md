# claude-code-tab-title

VS Code terminal tab titles that show what each Claude Code session is working on, with a busy/idle marker.

When you have multiple `claude` sessions running in different VS Code terminal tabs, the tab titles all collapse to the binary name (`2.1.119`) or to a static shell label, so you can't tell at a glance which session is doing what. This wires up two hooks that render each tab's title as `<marker> <topic>`:

- `*` when you've just submitted (Claude is working) → flips at `UserPromptSubmit`
- `·` when Claude has finished its turn (idle) → flips at `Stop`

The topic is set once, from the first prompt of the session, and stays sticky until the session ends.

## What it looks like

**One session, over a single turn:**

```
· fide-exam               ← SessionStart writes a project-name fallback
* Refactor auth flow      ← after your first prompt: topic seeded, marker = busy
· Refactor auth flow      ← Claude finishes the turn → marker flips to idle
* Refactor auth flow      ← you reply "ok do that part" → marker flips back to busy
                            (topic stays — sticky from first prompt)
· Refactor auth flow      ← Claude finishes → idle again
```

**Four parallel sessions in VS Code's integrated terminal panel** (each line is a tab):

```
* Auth refactor           ← Claude working on this one right now
· Stripe webhook          ← idle, waiting for you to reply
* Migration runner        ← Claude working
· Tab title hook          ← idle
```

If you've added the `--topic` instruction (see below), the topics get synthesized down to 2–4 word summaries instead of the literal first line of your prompt.

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
curl -fsSL https://raw.githubusercontent.com/franzvill/claude-code-tab-title/main/tab-state.py \
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

## Optional: meaningful topic via Claude itself

The default behavior takes the **literal first line** of your first prompt as the topic — useful but rarely a great summary ("Help me refactor the entire authentication flow including login" becomes `Help me refactor the entire au…`).

The script accepts an explicit override:

```bash
~/.claude/hooks/tab-state.py --topic "Auth refactor"
```

To have Claude itself synthesize a 2–4 word topic on the first response of every new session, add an instruction like this to your project's `CLAUDE.md` or a personal user-level instruction file:

> On the first response in any new session, run `~/.claude/hooks/tab-state.py --topic "<2–4 word topic>"` to set a meaningful tab title summarizing the user's first request.

The override sets the topic in the same per-session state the hook uses, so the marker keeps flipping correctly afterwards.

## How it works

**On `SessionStart`** — writes `· <cwd basename>` as a fallback title so the tab shows something predictable before the first prompt.

**On `UserPromptSubmit`** — if no topic is in state yet, takes the first non-empty line of the prompt (sliced to first 500 bytes for safety on huge paste-ins), saves it as the topic, and writes `* <topic>`. If a topic is already set, just rewrites the title with the `*` marker — the topic itself doesn't change.

**On `Stop`** — rewrites the title with the `·` marker, keeping the existing topic.

**With `--topic "X"`** — overwrites the topic and rewrites the title with whatever marker the session was last in.

**Why we walk the process tree to write OSC:** Claude Code spawns hooks with no controlling tty of their own (so hook stdout/stderr can't bleed into the conversation). Writing to `/dev/tty` from the hook silently fails. The script falls back to `ps -o tty=,ppid= -p $PPID` to find the parent claude's real pty (e.g. `/dev/ttys020`) and writes there directly, walking up to 10 hops if the parent itself has no tty.

**State** is per-session at `/tmp/claude-tab-<session_id>` — JSON with `topic`, `marker_state`, and `last_title`. Dedup on `last_title` means hooks that compose an unchanged title don't re-emit OSC sequences.

In `--topic` mode there's no stdin payload providing `session_id`, so the script walks the process tree looking for `~/.claude/sessions/<pid>.json` (which Claude Code maintains) and reads `sessionId` from there.

## Caveats

- **macOS only** as written. The tty lookup shells out to `ps`; Linux would need `/proc/<pid>/stat` (field 7 = controlling-tty device number).
- **VS Code integrated terminal** is the assumed display. iTerm2 / Terminal.app honor OSC titles too but the visual is just whatever the OSC wrote.
- **The marker is static**, not animated. We emit a literal `*` or `·` character.
- **Manual tab rename will be overwritten** by the next `UserPromptSubmit` or `Stop`. Disable the hook entries if you'd rather rename manually.
- **Existing hooks aren't clobbered** as long as you append rather than replace the JSON (manual install) or use the plugin (which adds hooks alongside any user-defined ones).

## Troubleshooting

If your tab titles show `2.1.119` or some other Claude-Code-written title instead of our `* <topic>`, two settings can force VS Code and Claude Code out of the way (rarely needed in current Claude Code 2.1.119, but worth trying):

- Add to `~/.claude/settings.json` env: `"CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"` — stops Claude Code from writing competing OSC titles.
- Add to VS Code's user `settings.json`: `"terminal.integrated.tabs.title": "${sequence}"` — forces VS Code to display whatever the terminal sets via OSC instead of the default `${process}` template.

## Customize

Open `tab-state.py` and edit:

| Constant | Default | Meaning |
|---|---|---|
| `TITLE_MAX` | 28 | max title length before truncation with `…` |
| `PROMPT_SLICE` | 500 | bytes of the prompt body the script will scan |
| `MARKER_WORKING` | `*` | character emitted while Claude is working |
| `MARKER_IDLE` | `·` | character emitted when Claude is idle |

## Uninstall

**Option A**: `/plugin uninstall tab-title@claude-code-tab-title`.

**Option B**: `rm ~/.claude/hooks/tab-state.py` and remove the three hook entries from `~/.claude/settings.json`.

## License

[MIT](LICENSE)
