# Local stability and validation

Updated: 2026-10-18. Working branch: `fix/stability`.
Local package version: `0.1.0b14+enhanced.20261018.1`, based on upstream b14.
This identifies the locally maintained build; no public release is published.

## Completed audit

All 14 original audit areas (A1–A9, B1–B3, C1–C2) have fixes and regression tests:

- Atomic JSON writes, bounded process locks, three-way configuration merges and
  rollback of failed saves, including watchlist order and option positions.
- SQLite locking, independent provider cache snapshots, bounded shutdown work
  and protection against publications after shutdown.
- Separate worker groups and request generations for prices, history, option
  expirations and chains. Superseded responses cannot replace current data.
- Search, sorting and tag filtering use the latest price snapshot. Unsafe tag
  characters do not become widget identifiers or markup.
- Fetch timestamps are distinct from provider quote/bar timestamps. Old cache
  entries without a fetch timestamp remain Unknown until successfully fetched.
  The compact `Last Refresh: HH:MM:SS` display is retained; details are tooltips.
  List timestamps follow the active tab, including empty/unfetched lists, and
  unrelated responses do not overwrite status on special tabs.
- Worker/provider errors end loading states and allow later refresh recovery.
  Refresh intervals are finite and at least one second.
- Structural configuration validation preserves damaged original files, creates
  separate recovery copies when possible and blocks writes to affected files
  until repair and restart. Unaffected files remain writable.
- Partial/empty option data is normalized before rendering; chart/renderer
  errors are contained. Missing underlying prices are unavailable rather than
  invented. The UI does not fetch HTTP metadata while rendering options.
- Ticker suggestions retain the full symbol. FRED yearly comparisons handle
  February 29 and select the nearest observation within 45 days.

## Maintenance after the audit

- `run_tests.sh` resolves the project directory, isolates personal configuration
  and caches, and preserves test and coverage-report failure exit statuses.
  Coverage is required by default; missing tools do not silently disable it.
- CI runs critical syntax/undefined-name lint, mypy over the complete package,
  and the same tests with branch measurement and an enforced 80% combined
  statement/branch coverage minimum.
  Python 3.10–3.14 remain in the CI matrix. Local validation is Python 3.14 on
  Linux; editing the workflow does not mean the remote matrix has run.
- Mypy now checks untyped function bodies and has no package-wide/module-wide
  `ignore_errors` exemptions. UI views declare their actual application type
  for static checking without changing runtime app properties or import order.
  Third-party missing stubs are still allowed. This is stronger checking, not
  a claim that every dynamic value has a precise static type.
- Enter on a watchlist ticker now handles the table's cell-selection event as
  well as row selection, and awaits the asynchronous editing handler. A real
  keypress regression verifies the mounted editor and cancellation.
  Deletion uses a Textual Coordinate. Modal validation handles missing results;
  quick-edit selections reject an unset Select value. News converts Rich Text
  to a string before passing it to Markdown. Option position callbacks retain
  the ticker selected when the dialog opened.
- `install.sh` uses an absolute project path, keeps existing global launchers
  by default and never upgrades pip automatically. Link creation is explicit,
  checks again after installation and uses atomic replacement. Regular files
  are never overwritten, including with the replacement flag.
- Pure quote-status formatting is extracted into `quote_status.py`; the main
  application's small wrapper keeps its prior interface and compact display.
  Larger architectural changes should be incremental and covered by tests.
- A validated Linux/Python 3.14 constraint snapshot is recorded under
  `requirements/validated-linux-py314.txt`; it supplements the portable project
  dependency ranges. It is not a cross-platform lock file.

The former mutation-testing CI command swallowed failures with `|| true`; that
misleading step is removed. Mutation analysis is available through the separate `mutation` extra, is not a
required gate, and is not claimed as performed by this validation. Broad
style-only Ruff findings are also not part of the critical lint gate.

## Latest local validation

The complete coverage-gated run on Linux/Python 3.14.4 discovered 829 tests:
827 passed and two opt-in live tests were skipped. Combined statement/branch
coverage was 90.90% against the enforced 80% minimum. Full-package mypy
(47 Python source files), critical Ruff checks, shell syntax and whitespace
checks passed. The tested runtime versions were preserved during installation.

## Reproducing validation

```bash
./install.sh --dev
./run_tests.sh
.venv/bin/mypy stockstui
.venv/bin/ruff check stockstui tests --select=E9,F63,F7,F82
```

For the validated Linux/Python 3.14 versions, install the checkout with
`python -m pip install -c requirements/validated-linux-py314.txt -e '.[dev]'`.
Select an explicit test interpreter with `STOCKSTUI_PYTHON` when necessary.
Test failure exits before the coverage report; low coverage exits nonzero.
Only both successful checks print the final success message. The explicit
`--no-coverage` option is intended for diagnostics, not the CI gate.

The suite uses synthetic prices and temporary configurations. Live network
checks are opt-in and skipped by default. Passing tests cannot guarantee
provider uptime or absence of every possible future defect.

## Installation and recovery

After validation, install the local wheel with `--no-deps` into the existing
pipx environment. Preserve runtime dependency versions and personal JSON files.
Restart running stocksTUI windows after installation to load all changed code.
The task outputs retain the preceding source backup and wheel for rollback.
Never restore older personal configuration over newer edits without comparison.
