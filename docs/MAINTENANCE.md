# Maintenance — stocksTUI Enhanced

Updated: 2026-10-18. Current release: **v1.0.4-enhanced**, package **1.0.4**.

## Repository and branches

The [enhanced repository](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced)
uses `main` as its default branch. `origin` points to this fork; `upstream` points
to [andriy-git/stocksTUI](https://github.com/andriy-git/stocksTUI). The current
upstream base is `v0.1.0-b14`.

Before maintenance, inspect the working tree and fetch changes:

```bash
git status --short --branch
git log --oneline --decorate -5
git fetch origin --prune
git fetch upstream --prune --tags
```

Fetching alone does not change local files. Preserve existing work, review
upstream differences, and use a feature branch for substantive changes. Do not
reset a modified checkout or blindly replace this fork with upstream files.

## Validation before merging

Prepare development dependencies and run the commands in [TESTING.md](TESTING.md).
The release gates are the complete unittest suite, at least **80% combined
statement/branch coverage**, full-package mypy and critical Ruff checks, plus
shell syntax and whitespace checks. GitHub Actions runs Python **3.10–3.14**.

Record the exact tested commit, environment, result counts and coverage. Keep
historical results labelled with their original build; they are not evidence for
untested later code. [VALIDATION.md](VALIDATION.md) records the published 1.0.4
baseline, and [STABILITY.md](STABILITY.md) records earlier maintenance rounds.

## Installing a tested version

A development checkout and the user's pipx application are separate environments.
`./install.sh` installs locally; `./install.sh --dev` adds development tools.
It preserves an existing global launcher. `--link` explicitly requests a launcher;
`--replace-launcher` is needed to replace another symlink, and regular files are
never overwritten. `--venv PATH` and `--bin-dir PATH` select locations.

For normal release installation, use the tagged command in the
[root README](../README.md#-installation). For an existing, validated pipx runtime,
a tested wheel can be installed without changing dependency versions:

```bash
pipx runpip stockstui install --no-deps /absolute/path/to/stockstui-1.0.4-py3-none-any.whl
stockstui --version
```

Check compatibility and dependencies before choosing `--no-deps`; a fresh
environment needs the normal dependency installation. Restart running application
windows after an update. `--offline --no-deps` on the development installer is
only suitable for an environment that already has dependencies and build tools.
The Linux/Python 3.14 constraints snapshot supplements the portable project
metadata; it is not a cross-platform lockfile.

## Backups and recovery

Before installation or manual configuration repair, close running application
instances and retain the previous wheel, source revision and user data outside
the checkout. On Linux, the standard locations are:

- Configuration: `~/.config/stockstui/` (`lists.json`, `portfolios.json`,
  `settings.json`, `themes.json`, and any recovery/journal files).
- SQLite data: `~/.cache/stockstui/app_cache.db`. This also contains **user-entered
  option positions**, so do not treat the entire database as disposable cache.
- Logs: `~/.cache/stockstui/stockstui.log`.

Locations can differ with platform or XDG settings. Back up SQLite only after
closing the application, including any remaining `-wal`/`-shm` sidecar files.
The common Linux pipx launcher is `~/.local/bin/stockstui`; use `pipx list` to
identify the actual environment on the target machine.

For damaged configuration, retain the original and recovery copies, repair or
restore the affected file while the application is closed, and restart.
Protected recovery sessions deliberately block writes to damaged files. Do not
remove a pending configuration transaction journal merely to bypass recovery.
Never overwrite newer personal edits with an old backup without comparison.
Rollback should use the retained compatible wheel and data backup.

## Publishing a future release

1. Choose the next version and update `pyproject.toml`, README, enhanced changelog,
   documentation and release highlights together. Keep package versions and tags
   consistent: package `1.0.4` corresponds to tag `v1.0.4-enhanced`.
2. Test the final source and record successful CI for the exact release commit.
3. Build and verify the wheel, its packaged resources, dependencies and checksum.
   Keep the previous working artifact and configuration backups.
4. Create an annotated tag on the tested commit, push it, and publish a GitHub
   release with the verified wheel and `SHA256SUMS.txt`.
5. Download the public artifact back and verify its bytes and checksum. Confirm
   the title, highlights, changelog link and version identify the same release.

Published tags and wheels remain fixed. Documentation-only corrections can be
committed to `main` without replacing the existing release; the bundled manual
then receives those corrections in a future package. Runtime changes require a
new tested package/version rather than silently replacing the published wheel.

See the [documentation index](README-ENHANCED.md#documentation) for the complete
set of guides and [CREDITS.md](CREDITS.md) for upstream attribution and licensing.
