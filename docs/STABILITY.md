# Local stability and validation

Updated: 2026-10-18. Working branch: `fix/stability`.
Local package version: `0.1.0b14+enhanced.20261018.3`, based on upstream b14.
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

## Additional failure-path review

- News and FRED workers snapshot their selection and reject superseded results,
  including callbacks already queued on the UI thread. Cancellation finishes the
  loading state, and global refresh retries news, history, options and FRED.
  Forced refresh bypasses or invalidates the relevant caches. Market-status
  messages also identify their calendar and request generation.
- News tolerates missing nested fields and timestamps, distinguishes an empty
  successful response from failure and keeps articles when another symbol fails.
  Valid articles without a URL remain visible as plain text. News and FRED
  caches return independent copies and reject older concurrent publications.
  FRED validates response shapes and does not include API-key URLs in errors.
- List rename/deletion commits settings references and list contents with a
  durable undo journal. Startup recovers interrupted transactions before loading;
  conflicting external edits preserve the journal and block writes for repair.
  Existing per-file locking and three-way merges still apply. Single-file saves
  synchronize the directory and retain the committed memory state if that final
  durability check is unsupported.
- List dialogs retain their original target after selection changes and reject
  deleted targets. Built-in tab names cannot be used for new lists; invalid saved
  configuration follows the existing protected-original recovery path. User list
  names, aliases and modal headings render literally, including square brackets.
- Provider and database numbers are normalized before merging and rendering.
  Invalid incoming values cannot replace valid cached prices, move fetch times
  or appear as infinity. Zero EPS/beta remain valid. Known splits invalidate
  cached figures in the previous share units rather than retaining pre-split highs.
- Partial historical frames and invalid volume/date values are handled before
  rendering. Charts preserve currency, label UTC and scale extreme finite prices
  internally while keeping original price labels; tick loops are bounded.
  Subnormal ranges retain both endpoints, and small/large values use readable
  scientific labels instead of rounding to zero or consuming the chart width.
- Log notifications dispatch correctly on both the UI thread and worker threads.
  Help/version/manual calls preserve diagnostic logs, and the notification
  handler is detached even when the application exits with an exception.

## Price integrity and persistence follow-up (.3)

- Price and metadata caches compare completed request generations under the
  cache lock. An older response cannot replace a newer completed publication;
  a newer pending request does not prevent an earlier result from making progress.
  Delayed failures cannot mark newer successful prices as failed.
- Persistent price merges reject older snapshots and preserve their newer expiry.
  Split-aware merges clear figures in old share units in SQLite as well as memory.
  Outdated split replies cannot relabel preserved prices with a wrong quote time.
- SQLite metadata retains quote type and pre/post-market support after restart.
  Migration adds nullable columns and preserves old rows. Missing legacy metadata
  is fetched again when necessary for refresh classification.
- Transient metadata failures remain retryable. Optional fast-info failures and
  incomplete OHLCV frames retain usable slow quotes and Close values. Zero EPS
  and beta remain valid; zero share counts do not mask valid fallback counts.
- Adding a ticker to every portfolio uses one atomic configuration save. A failed
  save rolls back the complete operation. Portfolio timestamps identify actual UTC.

## Latest local validation (.3)

The complete suite ran 912 tests against unchanged source: 910 passed and
2 opt-in live tests were skipped. All modules were measured in four isolated
processes, combined, and checked against the coverage gate. Combined statement/
branch coverage is 90.69%, above the required 80%. Both live provider checks
also passed separately after the final provider changes.

The follow-up adds 22 regression tests, including deterministic overlapping-call
orders, split persistence, old-schema migration and portfolio write failure.
Full-package mypy (49 source files), critical Ruff, shell syntax and whitespace
checks passed on Linux/Python 3.14.4. The other Python versions and remote CI
matrix were not run locally.

After installation, 106 regression tests passed against the actual pipx package
from outside the checkout. All 55 Python/resource files matched the verified wheel
and source (49 Python files). All 40 other distribution versions, the launcher
and four personal JSON files were unchanged. Dependency compatibility passed;
pipx metadata identifies the new local version. No public release was published.
The earlier candidate's overlap-starvation failure and superseded full-run results
are retained as intermediate evidence, rather than presented as final validation.

## Previous local validation (.2)

The complete suite discovered 890 tests: 888 passed and two opt-in live tests
were skipped. Both live tests also passed in a separate run against the public
provider. The suite was rerun in two isolated processes after updating obsolete
test expectations for literal Text cells and rejection of blank symbols. The
arbitrary-symbol property test retains its broad generator and adds a fixed
blank-symbol example.

Coverage was measured on a complete instrumented run. After the last isolated
chart correction, the old chart-module data was purged and the entire module
was measured again with 56 focused tests, all passing. Other production files
are byte-identical to the complete measurement. Final combined statement/branch
coverage is 90.62%, above the enforced 80% minimum. The logs preserve failed
intermediate expectations and distinguish the full suite from this recheck.

Full-package mypy (49 source files), critical Ruff, shell syntax and whitespace
checks passed on Linux/Python 3.14.4. Runtime dependency versions were preserved;
the constraints snapshot records the actual runtime and validation tools used.
Other Python versions and the remote CI matrix were not run locally.

After installation, 84 regression tests passed against the actual pipx package
from outside the source checkout. All 55 Python/resource files matched the wheel
and source (49 Python files). All 40 other distribution versions, the launcher
and the four personal JSON files were unchanged. Dependency compatibility passed,
and pipx's package-version metadata matches the installed local build.

## Previous local validation (.1)

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
