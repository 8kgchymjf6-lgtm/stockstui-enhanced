# CHANGELOG - StockSTUI Enhanced

This changelog documents all enhancements introduced in the locally maintained
StockSTUI Enhanced edition relative to upstream release `v0.1.0-b14`.

The original upstream project history remains available in the repository's
`CHANGELOG.md`.

---

# v1.0.4-enhanced

Release date:

- 2026-10-18

Base release:

- stocksTUI v0.1.0-b14

Previous enhanced release:

- v1.0.3-enhanced

Package version:

- 1.0.4

Release type:

- Stability, data integrity, and maintenance release

Maintenance release focused on quote integrity, safe watchlist storage, and reliable refresh recovery.

## Highlights

- Added atomic configuration saves, rollback and recovery of interrupted watchlist changes, with protection against overwriting damaged original files
- Fixed concurrent quote and SQLite cache updates, including stale responses and incorrect figures after stock splits, saves, and restarts
- Improved refresh retries and loading-state recovery across prices, history, news, options, and FRED; outdated results no longer replace the active selection
- Fixed watchlist search, sorting, tag filtering, and editing; aliases and list names now render literally in the interface and terminal output
- Restored the compact Last Refresh display, kept timestamps specific to the active tab, and separated fetch times from quote and bar times
- Improved handling of partial provider responses and invalid numbers, and prevented history and open-interest charts from failing or hanging on extreme data
- Fixed ticker completion, Enter editing, Vim navigation, empty-table actions, option expiration-day display, and FRED leap-year comparisons
- Expanded regression coverage to 922 passing tests with 2 expected skips and 92.31% total statement/branch coverage; CI passes on Python 3.10–3.14

## Additional fixes and maintenance

- Adding a ticker to every portfolio now commits as one atomic operation;
  failed writes roll back the complete operation. Portfolio timestamps use UTC.
- Ticker metadata retains quote type and pre/post-market support after restart.
  Existing SQLite tables migrate without deleting their rows.
- Help, version and manual calls preserve diagnostic logs. Notifications are
  dispatched on the correct thread, and the handler is detached on exit.
- Installation scripts preserve existing launchers and resolve the project path.
  Test scripts isolate personal configuration, require coverage by default and
  preserve failure exit statuses. CI enforces the coverage threshold.
- Package metadata, installation instructions and project links identify this
  enhanced edition as version 1.0.4. Upstream attribution and licensing remain.

## Release verification

- Complete local suite: **924 tests: 922 passed, 2 optional live checks skipped**.
- Local combined statement/branch coverage: **92.31%**, minimum **80%**.
- Main Textual application statement/branch coverage: **84.48%**.
- **118 regression tests** passed against the installed 1.0.4 package.
- Full-package mypy, critical Ruff, shell syntax and whitespace checks passed.
- [GitHub CI](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/actions/runs/39138313029)
  passed on Python **3.10, 3.11, 3.12, 3.13 and 3.14**, running the complete
  **924-test suite** with two opt-in live checks skipped and enforcing the
  coverage gate on every version.
- One UTC timestamp assertion was made portable to Python 3.10 without changing
  its expected instant; the complete GitHub matrix passed after this adjustment.
- The release wheel was downloaded from GitHub and verified against its SHA-256
  checksum. The local upgrade preserved all 40 other dependency versions, the
  launcher and the four personal JSON files.

These changes promote the measured local stability build; the production code
is unchanged by release preparation. Coverage is a measure of testing and does
not guarantee absence of every defect. See [STABILITY.md](STABILITY.md) for
validation details, platform scope and recovery guidance.

---

# v1.0.3-enhanced

Release date:

- 2026-08-04

Base release:

- stocksTUI v0.1.0-b14

Previous enhanced release:

- v1.0.2-enhanced

Release type:

- Test coverage, regression safety, and maintenance release

Source-code statistics since v1.0.2-enhanced:

- 10,765 insertions
- 18 deletions
- 24 files changed

---

# Testing and quality assurance

## Added

- Added comprehensive regression coverage for the main Textual application.
- Added dedicated coverage tests for FRED and market data providers.
- Added dedicated coverage tests for the options provider.
- Added extensive tests for database behavior and persistence.
- Added tests for configuration management and configuration views.
- Added comprehensive tests for modal dialogs.
- Added tests for tag filtering and utility helpers.
- Added tests for history and open-interest charts.
- Added expanded coverage for History, News, FRED, Options, and Debug views.
- Added broader keyboard-navigation and application-state coverage.
- Added coverage for price-table formatting, sorting, workers, message handlers,
  open mode, search behavior, and view transitions.

## Improved

- Increased total project coverage to 89.05%.
- Increased `stockstui/main.py` coverage to 70.04%.
- Expanded the test suite to 712 passing tests.
- Improved branch coverage across data providers, views, widgets, configuration,
  formatting, database, and application orchestration.
- Improved isolation of network-dependent tests.
- Improved test reliability across the supported Python versions.
- Improved regression protection for the enhanced release line.

## Changed

- Live API tests are now skipped by default to keep normal test runs reliable and
  independent of external services.
- Live API tests remain available for explicit integration testing.

---

# FRED validation

## Fixed

- Corrected FRED series input validation to validate the current submitted value
  directly.
- Updated validation error handling to display the descriptions from the actual
  validation failures.
- Prevented stale widget validation state from incorrectly accepting or rejecting
  FRED series input.

---

# Release verification

- Full test suite: 712 tests passed.
- Expected skips: 2.
- Ruff checks passed.
- Ruff formatting checks passed.
- Git whitespace checks passed.
- Total coverage: 89.05%.
- `stockstui/main.py` coverage: 70.04%.

---

# v1.0.2-enhanced

Release date:

- 2026-08-02

Base release:

- stocksTUI v0.1.0-b14

Previous enhanced release:

- v1.0.1-enhanced

Release type:

- Numeric display, test maintenance, and CI compatibility release

Changes since v1.0.1-enhanced:

- 8 files changed
- 33 insertions
- 18 deletions

Maintenance release focused on missing numeric values, regression checks, and CI compatibility.

## Highlights

- Rendered missing EPS, PE Ratio and Beta values as N/A, avoiding numeric conversion errors in the price table
- Updated formatter tests for compact volumes, prices and price ranges, and isolated the startup-tab test from configured crypto tickers
- Limited CI Ruff checks to critical errors and removed automatic source rewrites
- Updated GitHub Actions checkout and setup-python to v6
- Migrated mutmut configuration to source paths and explicit formatter-test selection
- Improved the enhanced-edition README notice and Python bytecode cache exclusions
- CI passes on Python 3.10–3.14

## Release verification and scope

- [Historical release CI](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/actions/runs/30760392719)
  passed on Python **3.10, 3.11, 3.12, 3.13 and 3.14** for tagged commit
  `ee998685dbb26d326bd99d7eb70a0296e07888a3`.
- The runtime change handles `None` explicitly for EPS, PE Ratio and Beta before
  numeric conversion, displaying missing values as `N/A`. The original short
  release note described this only as mypy compatibility.
- Formatter assertions were aligned with the already enhanced output; this
  release did not introduce the earlier sorting and formatting features again.
- This historical CI ran critical Ruff, mypy and the then-current test workflow.
  Its mutation-test command allowed failures; it was not a strict mutation gate.
  The current 1.0.4 test counts, coverage figures and coverage gate must not be
  attributed to this older release.

---

# v1.0.0-enhanced

Release date:

- 2026-08-02

Base release:

- stocksTUI v0.1.0-b14

Modified source files:

- `stockstui/main.py`
- `stockstui/presentation/formatter.py`
- `stockstui/data_providers/market_provider.py`

Source-code statistics:

- 282 insertions
- 48 deletions

---

# User interface

## Added

- Added keyboard shortcut **H** for sorting by High values.
- Added keyboard shortcut **L** for sorting by Low values.

## Improved

- Improved default Description sorting.
- Improved History view sorting.
- Improved sort-direction handling.
- Improved overall sorting consistency.
- Improved runtime robustness during sorting operations.

## Fixed

- Corrected Open sorting behaviour.
- Prevented sorting failures when the Ticker column is hidden.
- Improved handling of hidden columns during keyboard sorting.

---

# Financial data formatting

## Improved

- Improved Market Cap formatting.
- Improved Volume formatting.
- Improved currency formatting.
- Improved price formatting.
- Improved percentage formatting.
- Improved PE Ratio formatting.
- Improved Dividend Yield formatting.
- Improved financial-value presentation.
- Improved table consistency.
- Left-aligned ticker symbols for improved readability.

---

# Numeric sorting

## Improved

- Improved sorting of formatted numeric values.
- Added support for compact K values.
- Added support for compact M values.
- Added support for compact B values.
- Added support for compact T values.
- Improved sorting consistency for formatted financial values.

---

# Market data

## Improved

- Improved PE Ratio selection logic.
- Improved Dividend Yield normalization.
- Improved fallback handling for incomplete Yahoo Finance data.
- Improved handling of missing financial values.

---

# Application robustness

## Improved

- Added defensive validation before sorting.
- Improved handling of invalid values.
- Improved runtime stability.
- Improved consistency across sorting operations.
- Reduced the risk of runtime failures caused by incomplete data.

---

# Documentation

The enhanced edition introduces dedicated project documentation covering:

- Enhanced project overview.
- Technical implementation.
- Validation.
- Testing.
- Maintenance.
- Credits.

---


# Compatibility

The enhanced edition preserves:

- Original project structure.
- Original licensing.
- Original attribution.
- Upstream compatibility wherever practical.

---

# Summary

The initial `v1.0.0-enhanced` changes were limited to three Python files.
Subsequent releases extend regression coverage and stability improvements across
configuration, persistence, providers, widgets and the main application.
Current scope and validation are recorded in [STABILITY.md](STABILITY.md).
