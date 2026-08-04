# CHANGELOG - StockSTUI Enhanced

This changelog documents all enhancements introduced in the locally maintained
StockSTUI Enhanced edition relative to upstream release `v0.1.0-b14`.

The original upstream project history remains available in the repository's
`CHANGELOG.md`.

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

Compared with upstream release `v0.1.0-b14`, StockSTUI Enhanced introduces a
carefully maintained collection of usability improvements, sorting
enhancements, financial-data formatting improvements, defensive programming
improvements and project documentation while intentionally limiting source-code
changes to three Python files.
