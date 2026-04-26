# claude-code-tab-title

VS Code terminal tab titles that show what each Claude Code session is currently working on.

When you have multiple `claude` sessions running in different VS Code terminal tabs, the tab titles all collapse to the binary name (`2.1.119`) or to a static shell label, so you can't tell at a glance which session is doing what. This wires up a `UserPromptSubmit` hook that updates each tab's title with the topic of your last substantive prompt.

## What you get

- Tab title = the topic of your last substantive prompt.
- **Sticky** across short follow-ups: any reply under `MIN_TOPIC_LEN` chars (default 10) keeps the previous topic in place — `ok`, `do it`, `fix it`, `next` all leave the topic alone. Anything longer replaces it. Length-only check, no English-specific word list.
- **No emoji prefix** — VS Code's native `·`/`✱` tab indicator handles the busy/idle visual.
- **No flicker on tool calls.** `PreToolUse` is intentionally not hooked.
- **No LLM call.** Pure heuristic from your prompt text. Zero token cost.

## Requirements

- macOS. The script uses `ps -o tty=` to find the parent `claude` process's controlling pty (hooks lose `/dev/tty` because Claude Code isolates them — more on that in [How it works](#how-it-works)). Linux would need a `/proc/<pid>/stat` reader instead.
- VS Code with the integrated terminal. Other terminals (iTerm2, Terminal.app, Ghostty) handle OSC titles fine but their busy/idle indicators differ.
- Claude Code v2.x. Tested against `2.1.119`.

## Install

### 1. Drop the hook script

```bash
mkdir -p ~/.claude/hooks
curl -fsSL https://raw.githubusercontent.com/franzvill/claude-code-tab-title/main/tab-state.py \
  -o ~/.claude/hooks/tab-state.py
chmod +x ~/.claude/hooks/tab-state.py
```

### 2. Wire it up in `~/.claude/settings.json`

You need three things in this file: `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` in the `env` block, and two hook entries.

If you don't have `~/.claude/settings.json` yet, this is the whole file:

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

If you already have `settings.json`, **merge** these into your existing config — don't replace the whole file. Specifically:

- Add `"CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1"` to the existing `env` object (this stops Claude Code itself from writing a competing title).
- Append the two new hook entries to the `UserPromptSubmit` and `SessionStart` arrays. If you already have hooks for those events (e.g. `ccnotify`, sound notifiers), add a *new* `{ "hooks": [...] }` block alongside them — both will fire.

### 3. Tell VS Code to honor OSC title sequences

VS Code's terminal defaults `terminal.integrated.tabs.title` to `${process}`, which shows the foreground process's filename. Since Claude Code's binary is literally named `2.1.119` (the version), every Claude tab ends up titled `2.1.119` and your OSC writes are ignored.

Open VS Code's user `settings.json` (`Cmd+Shift+P` → "Preferences: Open User Settings (JSON)") and add:

```json
"terminal.integrated.tabs.title": "${sequence}"
```

This makes VS Code display whatever the terminal last set via OSC `\033]0;TITLE\007`, which is exactly what the hook writes.

### 4. Restart and test

Open a fresh VS Code terminal tab. Run `claude`. Submit a prompt like *"Refactor the auth flow"*. The tab title should update to that topic. Reply `ok do that` — the topic stays. Reply `Now also fix login` — the topic replaces.

Existing `claude` sessions don't pick up new hooks until restart.

## How it works

**On `SessionStart`:** writes the cwd basename (e.g. `fide-exam`) as a fallback title, so the tab shows something predictable before the first message.

**On `UserPromptSubmit`:** reads the JSON payload from stdin, slices `prompt` to the first 500 bytes (so a 50 KB paste-in doesn't cost anything), takes the first non-empty line. If `topic` is empty (first message ever) or the prompt's stripped length is at least `MIN_TOPIC_LEN`, replaces topic with that line. Otherwise keeps the existing topic. Composes the title (truncated to 26 chars, control chars stripped) and writes OSC.

**Continuation detection:** length-only. A prompt under `MIN_TOPIC_LEN` chars (default 10) is a continuation and leaves the topic alone; everything else replaces it. No hardcoded ack words — works in any language and stays maintainable.

**Why we walk the process tree to write OSC:** Claude Code spawns hooks without a connected `/dev/tty` (presumably so hook stdout/stderr doesn't leak into the conversation). Writing to `/dev/tty` from the hook silently fails. The script falls back to `ps -o tty=,ppid= -p $PPID` to find the parent `claude`'s real pty (e.g. `/dev/ttys020`) and writes there directly, walking up to 10 hops if the parent itself has no tty.

**State** is per-session at `/tmp/claude-tab-<session_id>` — JSON with `topic` and `last_title`. Dedup on `last_title` means hooks that compose an unchanged title don't re-emit OSC sequences.

## Caveats

- **macOS only** as written. The `find_terminal_device()` function shells out to `ps`; Linux'd want `/proc/<pid>/stat`.
- **VS Code integrated terminal** is the assumed display. iTerm2 / Terminal.app honor OSC titles too but the busy/idle indicator (`·`/`✱`) is VS Code-specific.
- **No semantic compression.** The title is the literal first line of your last substantive prompt, truncated. *"Help me refactor the entire authentication flow including login"* shows as `Help me refactor the ent…`. If you want 2–4 word topics, you need an LLM in the loop — see [Future work](#future-work).
- **Length-based continuation detection is imperfect.** A medium-length follow-up like `ok do the remaining stuff now` (29 chars) overwrites the topic, even though it's clearly a continuation in context. The fix would be an LLM-derived topic (see [Future work](#future-work)); the length-only check is the simplest thing that doesn't require a hardcoded English ack list.
- **Existing hooks aren't clobbered.** If you have `ccnotify` or similar already on `UserPromptSubmit`/`SessionStart`, our hook runs alongside, not in place of it — but only because you append rather than replace during step 2.

## Customize

Open `~/.claude/hooks/tab-state.py` and edit:

| Constant | Default | Meaning |
|---|---|---|
| `TITLE_MAX` | 26 | max display length before truncation with `…` |
| `PROMPT_SLICE` | 500 | bytes of prompt body the script will scan |
| `MIN_TOPIC_LEN` | 10 | length below which a prompt is a continuation (does not overwrite the topic) |

## Future work

- **LLM-derived topic** (PRs welcome): swap the heuristic for a fire-and-forget background call to a small model (e.g. `gpt-4o-mini`, Claude Haiku) that synthesizes a 2–4 word topic from the prompt. The hook could write the literal topic immediately, then refine in the background once the LLM returns.
- **Linux support**: replace `ps -o tty=,ppid=` with `/proc/<pid>/stat` field 7 (controlling tty as a device number) and resolve via `/dev`.
- **Manual override**: a `tab-state.py --topic "Refactor auth"` mode so Claude (or you, via a slash command) can set the topic explicitly.

## Uninstall

```bash
rm ~/.claude/hooks/tab-state.py
```

Then in `~/.claude/settings.json` remove the two hook entries you added in step 2 and the `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` line. In VS Code's user `settings.json` remove `terminal.integrated.tabs.title`.

## License

[MIT](LICENSE)
