# stocksTUI Enhanced

This independently maintained fork of
[andriy-git/stocksTUI](https://github.com/andriy-git/stocksTUI) combines the original
sorting and formatting enhancements with configuration, quote/cache, worker and
interface stability fixes. Upstream history, attribution and licensing are retained.

## Current release

- Repository: [stockstui-enhanced](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced)
- Release: [v1.0.4-enhanced](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/releases/tag/v1.0.4-enhanced)
- Package version: **1.0.4**; upstream base: **v0.1.0-b14**.
- Default branch: **main**.
- License: [GNU GPL v3.0 or later](../LICENSE).

## Changes since 1.0.3

Atomic configuration and watchlist saves, protected recovery, synchronized quote
and SQLite updates, stale-response protection, refresh retries, literal user
labels, search/filter/sort corrections and the compact per-tab Last Refresh
status are included. Options, FRED, input/navigation and chart edge cases also
have regression coverage. See the [complete release highlights](CHANGELOG-ENHANCED.md#v104-enhanced).

The original three-file enhancement description is historical; subsequent
maintenance spans providers, configuration, persistence, views and tests.

## Validation

Local Linux/Python 3.14 checks: **922 tests passed, 2 optional live checks skipped**,
with **92.31% combined statement/branch coverage**. The complete release CI also
passed on **Python 3.10–3.14**. Coverage is not a reliability percentage; full
provenance and limits are recorded in [VALIDATION.md](VALIDATION.md).

## Documentation

- [Installation and examples](../README.md)
- [Enhanced changelog](CHANGELOG-ENHANCED.md)
- [Technical overview](TECHNICAL-OVERVIEW.md)
- [Release validation](VALIDATION.md)
- [Testing commands and quality gates](TESTING.md)
- [Detailed stability audit and historical results](STABILITY.md)
- [Maintenance, backups and releases](MAINTENANCE.md)
- [Full source user manual](../stockstui/documents/help.txt)
- [Credits and license](CREDITS.md)
- [Original upstream changelog](../CHANGELOG.md)

The release tag records the published source; `main` also contains subsequent
documentation corrections. A frozen release wheel retains the manual packaged
when it was built.
