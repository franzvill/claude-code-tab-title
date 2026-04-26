# claude-code-tab-title

VS Code terminal tab titles that show what each Claude Code session is working on, with a busy/idle marker.

When you have multiple `claude` sessions running in different VS Code terminal tabs, the tab titles all collapse to the binary name (`2.1.119`) or to a static shell label, so you can't tell at a glance which session is doing what. This wires up two hooks that render each tab's title as `<marker> <topic>`:

- `*` when the user has just submitted (Claude is working) → flips at `UserPromptSubmit`
- `·` when Claude has finished its turn (idle) → flips at `Stop`

The topic is set once, from the first prompt of the session, and stays sticky until the session ends.

## Install

### 1. Drop the hook script

```bash
mkdir -p ~/.claude/hooks
curl -fsSL https://raw.githubusercontent.com/franzvill/claude-code-tab-title/main/tab-state.py \
  -o ~/.claude/hooks/tab-state.py
chmod +x ~/.claude/hooks/tab-state.py
```

### 2. Wire it up in `~/.claude/settings.json`

You need an env var (so Claude Code stops writing competing titles) plus three hooks. If you don't have `~/.claude/settings.json` yet, this is the whole file:

```json
{
  "env": {
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "~/.claude/hooks/tab-state.py working" }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "~/.claude/hooks/tab-state.py idle" }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "~/.claude/hooks/tab-state.py idle" }
        ]
      }
    ]
  }
}
```

If you already have `settings.json`, **merge** these in — don't replace the whole file. Add `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` to the existing `env` object. For the hooks: if `UserPromptSubmit`, `Stop`, or `SessionStart` already exist (e.g. for `ccnotify` or other sound/notifier hooks), append a new `{ "hooks": [...] }` block beside the existing ones — both will fire.

### 3. Tell VS Code to honor OSC title sequences

VS Code's terminal defaults `terminal.integrated.tabs.title` to `${process}`, which shows the foreground process's filename — and since Claude Code's binary is named `2.1.119` (the version), every claude tab ends up titled `2.1.119` and your OSC writes are ignored.

Open VS Code's user `settings.json` (`Cmd+Shift+P` → "Preferences: Open User Settings (JSON)") and add:

```json
"terminal.integrated.tabs.title": "${sequence}"
```

VS Code will then display whatever the terminal last set via OSC, which is what the hook writes.

### 4. Restart and test

Open a fresh VS Code terminal tab. Run `claude`. Submit any prompt longer than a few words — the tab will become `* <first line of your prompt>`. When Claude finishes the turn the prefix flips to `·`. Subsequent prompts don't change the topic; it sticks to whatever was set on the first prompt.

Existing claude sessions don't pick up the new hooks (or the env var) until restart.

## Optional: meaningful topic via Claude itself

The default behavior takes the **literal first line** of your first prompt as the topic — useful but rarely a great summary ("Help me refactor the entire authentication flow including login" becomes `Help me refactor the entire au…`).

The script accepts an explicit override:

```bash
~/.claude/hooks/tab-state.py --topic "Auth refactor"
```

You can have Claude itself synthesize a 2–4 word topic and call this on the first response of every new session. To make it automatic, drop something like this into your project's `CLAUDE.md` or a personal user instruction:

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
- **VS Code integrated terminal** is the assumed display. iTerm2 / Terminal.app honor OSC titles too but the visual is just whatever the OSC wrote — there's no separate VS Code-style busy indicator.
- **The marker is static**, not animated. We emit a literal `*` or `·` character. Claude Code's own native indicator (which may animate) is disabled by `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` because otherwise it stomps on our title.
- **Manual tab rename will be overwritten.** Any OSC write replaces the tab's manual rename. You can rename, but the next `UserPromptSubmit` or `Stop` will overwrite. Disable the hook entries if you'd rather rename manually.
- **Existing hooks aren't clobbered** as long as you append rather than replace during step 2.

## Customize

Open `~/.claude/hooks/tab-state.py` and edit:

| Constant | Default | Meaning |
|---|---|---|
| `TITLE_MAX` | 28 | max title length before truncation with `…` |
| `PROMPT_SLICE` | 500 | bytes of the prompt body the script will scan |
| `MARKER_WORKING` | `*` | character emitted while Claude is working |
| `MARKER_IDLE` | `·` | character emitted when Claude is idle |

## Uninstall

```bash
rm ~/.claude/hooks/tab-state.py
```

Then in `~/.claude/settings.json` remove the three hook entries you added (`UserPromptSubmit`, `Stop`, `SessionStart`) and the `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` line. In VS Code's user `settings.json` remove `terminal.integrated.tabs.title`.

## License

[MIT](LICENSE)
