# Blockers

Things that stopped a verification step. Each one says what was tried and how to unblock it.

## 1. CI could not run: the `gh` token lacks the `workflow` scope

- **What happened:** the private CI repo `rajfctrz/localproof-ci` was created, but `git push ci main` was rejected:
  `refusing to allow an OAuth App to create or update workflow .github/workflows/build.yml without workflow scope`.
  GitHub requires the `workflow` scope for any push that adds or changes a file under `.github/workflows/`, so no commit containing the workflow can be pushed with the current token.
- **Token scopes found:** account `rajfctrz` (active): `gist, read:org, repo`. A second login on this machine, `rajeshmr`, has `workflow`, but it is a different identity, so it was not switched to without the owner's decision.
- **Effect:** none of the GitHub Actions jobs (Windows, macOS x86_64, AppImage x86_64, Flatpak x86_64, release/SBOM) has run. Everything that needed CI is listed in [MANUAL_CHECKS.md](MANUAL_CHECKS.md).
- **To unblock** (either):
  ```bash
  gh auth refresh -h github.com -s workflow     # interactive: approve in the browser
  git push ci main
  gh run watch -R rajfctrz/localproof-ci
  ```
  or push with the account that has the scope (`gh auth switch -u rajeshmr`), after giving it access to the repo.
- **Cost note:** on a private repo, GitHub bills macOS runner minutes at 10x. One full run uses roughly 2 macOS jobs x ~10 min.

## 2. DMG Finder layout step times out locally (not blocking)

- `create-dmg` arranges the DMG window through Finder AppleScript, which timed out (`AppleEvent timed out (-1712)`) because the terminal has no Automation permission for Finder.
- Worked around with `DMG_SKIP_FINDER=1` (`--skip-jenkins`), which CI uses too. The DMG is valid and verified; only the icon layout inside the window is skipped.
- To get the laid-out DMG locally: System Settings → Privacy & Security → Automation → allow your terminal to control Finder, then run `packaging/macos/make_dmg.sh` without the variable.
