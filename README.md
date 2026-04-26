# claude-code-tab-title

VS Code terminal tab titles that show what each Claude Code session is working on, with a busy/idle marker.

When you have multiple `claude` sessions running in different VS Code terminal tabs, the tab titles all collapse to the binary name (`2.1.119`) or to a static shell label, so you can't tell at a glance which session is doing what. This wires up two hooks that render each tab's title as `<marker> <topic>`:

- `*` when you've just submitted (Claude is working) → flips at `UserPromptSubmit`
- `·` when Claude has finished its turn (idle) → flips at `Stop`

The topic is set once, from the first prompt of the session, and stays sticky until the session ends.

## Install

### Option A — via Claude Code plugin (recommended)

Two slash commands in any claude session:

```
/plugin marketplace add franzvill/claude-code-tab-title
/plugin install tab-title@claude-code-tab-title
```

That installs `tab-state.py` and registers the three hooks (`UserPromptSubmit`, `Stop`, `SessionStart`). You then need to do **two small manual steps** that plugins can't do on your behalf:

1. **Add the env var** to `~/.claude/settings.json` so Claude Code stops writing competing OSC titles:

   ```json
   {
     "env": {
       "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"
     }
   }
   ```

   (Merge into the existing `env` object if you already have one.)

2. **Tell VS Code to display OSC titles.** In `~/Library/Application Support/Code/User/settings.json` (Cmd+Shift+P → "Preferences: Open User Settings (JSON)"):

   ```json
   "terminal.integrated.tabs.title": "${sequence}"
   ```

Restart any running `claude` session for the env var to take effect.

To update later: `/plugin marketplace update`. To uninstall: `/plugin uninstall tab-title@claude-code-tab-title`.

### Option B — manual install

If you'd rather not use the plugin system:

1. Drop the script:

   ```bash
   mkdir -p ~/.claude/hooks
   curl -fsSL https://raw.githubusercontent.com/franzvill/claude-code-tab-title/main/tab-state.py \
     -o ~/.claude/hooks/tab-state.py
   chmod +x ~/.claude/hooks/tab-state.py
   ```

2. Add to `~/.claude/settings.json` (merge into existing `env` and `hooks` objects rather than replacing):

   ```json
   {
     "env": {
       "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"
     },
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

3. Add `"terminal.integrated.tabs.title": "${sequence}"` to VS Code's user `settings.json` (same as Option A step 2).

## Optional: meaningful topic via Claude itself

The default behavior takes the **literal first line** of your first prompt as the topic — useful but rarely a great summary ("Help me refactor the entire authentication flow including login" becomes `Help me refactor the entire au…`).

The script accepts an explicit override:

```bash
~/.claude/hooks/tab-state.py --topic "Auth refactor"
```

You can have Claude itself synthesize a 2–4 word topic and call this on the first response of every new session. To make it automatic, add an instruction like this to your project's `CLAUDE.md` or a personal user-level instruction:

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
- **Existing hooks aren't clobbered** as long as you append rather than replace the JSON (manual install) or use the plugin (which adds hooks alongside any user-defined ones).
- **Plugins can't set env vars on your behalf** — `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` and the VS Code setting both have to be added by hand even via Option A. There are only two manual lines either way.

## Customize

Open `~/.claude/hooks/tab-state.py` (Option B) or the plugin's installed copy at `~/.claude/plugins/...` (Option A) and edit:

| Constant | Default | Meaning |
|---|---|---|
| `TITLE_MAX` | 28 | max title length before truncation with `…` |
| `PROMPT_SLICE` | 500 | bytes of the prompt body the script will scan |
| `MARKER_WORKING` | `*` | character emitted while Claude is working |
| `MARKER_IDLE` | `·` | character emitted when Claude is idle |

## Uninstall

**Option A**: `/plugin uninstall tab-title@claude-code-tab-title`. Then remove `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` from `~/.claude/settings.json` and `terminal.integrated.tabs.title` from VS Code's user `settings.json`.

**Option B**: `rm ~/.claude/hooks/tab-state.py`, then remove the three hook entries from `~/.claude/settings.json`, the `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` env var, and the VS Code line.

## License

[MIT](LICENSE)
