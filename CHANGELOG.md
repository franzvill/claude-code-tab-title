# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Konsole (KDE Plasma) backend via DBus, gated on `$KONSOLE_DBUS_SERVICE`. Konsole silently ignores OSC title sequences emitted from non-foreground subprocesses on the same pty, so the existing OSC path is a no-op there. The DBus path uses `qdbus6` / `qdbus-qt6` / `qdbus` (whichever is on `PATH`) to call `org.kde.konsole.Session.setTitle` directly, which works regardless of process group.

## [0.1.0] - 2026-04-27

### Added
- Initial public release.
- `tab-title` plugin with `UserPromptSubmit`, `Stop`, and `SessionStart` hooks.
- Sticky topic extraction from first prompt of each session.
- Busy (`*`) / idle (`·`) marker.
- Process-tree tty walk for hooks spawned without a controlling tty.
- Tested in VS Code integrated terminal, iTerm2, and Terminal.app.
