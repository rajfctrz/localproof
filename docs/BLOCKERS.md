# Blockers

Things that stopped a verification step. Each one says what was tried and how to unblock it.

## 1. CI push blocked by token scope (resolved)

The first push of the workflow file was rejected because the `gh` token lacked the `workflow` scope. Resolved by the owner running `gh auth refresh -h github.com -s workflow`; CI went green on the third run, and on the public repo in run `40905976169`.

## 2. DMG Finder layout step times out locally (not blocking)

- `create-dmg` arranges the DMG window through Finder AppleScript, which timed out (`AppleEvent timed out (-1712)`) because the terminal has no Automation permission for Finder.
- Worked around with `DMG_SKIP_FINDER=1` (`--skip-jenkins`), which CI uses too. The DMG is valid and verified; only the icon layout inside the window is skipped.
- To get the laid-out DMG locally: System Settings → Privacy & Security → Automation → allow your terminal to control Finder, then run `packaging/macos/make_dmg.sh` without the variable.
