# Technical overview — stocksTUI Enhanced

Updated: 2026-10-18. Package: **1.0.4**. Release: **v1.0.4-enhanced**.
Upstream base: **v0.1.0-b14**. Default branch: **main**.

The [enhanced repository](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced)
retains the upstream Textual architecture. Changes since the original enhanced
edition cover providers, configuration, persistence, views, workers and tests.

## Application and presentation

- `stockstui/main.py` coordinates the application lifecycle, active tabs,
  worker requests, table updates, search, sorting and tag filters.
- `stockstui/parser.py` defines the CLI. `--fred` selects the configured FRED
  view and takes no series argument. `--tags` filters CLI output.
- `stockstui/quote_status.py` and `stockstui/quote_time.py` distinguish fetch
  times from provider quote/bar times. The compact Last Refresh line follows
  the active tab; detailed status is available in its tooltip. A missing known
  fetch time is shown as Unknown rather than inferred from an old market bar.
- `stockstui/presentation/formatter.py` formats financial values and tables.
  User aliases and list names render literally rather than as Rich markup.
- `stockstui/ui/` contains views, dialogs, input suggestions and charts.
  History and open-interest charts normalize invalid or extreme numeric data
  before rendering, and view errors release loading states for later retries.

## Configuration and persistence

- `stockstui/config_manager.py` and `stockstui/config_validation.py` handle
  atomic JSON replacement, bounded process locks, three-way merges, validation
  and protected recovery. Damaged originals are preserved; affected files
  remain protected until repair and restart.
- `stockstui/config_transaction.py` journals changes that update settings and
  watchlists together. Interrupted uncommitted changes can be rolled back
  without silently overwriting unrelated external edits.
- `stockstui/database/db_manager.py` serializes SQLite operations and stores
  cached market data, metadata and user-entered option positions. The database
  is not exclusively disposable cache data.
- `stockstui/data_providers/` retrieves prices, history, news, option chains and
  FRED observations and manages portfolio changes. Quote publication and
  persistent cache snapshots are synchronized to prevent stale writes.
- `stockstui/data_validation.py` normalizes provider/cache numbers and historical
  frames without modifying the input. Missing or invalid values stay unavailable.

## Asynchronous boundaries

Prices, history, news, option expirations/chains and FRED use request identity or
current-selection checks before applying results. Superseded work cannot replace
an active selection. Cancellation alone does not stop a provider thread, so
price/cache publication also uses synchronization. Worker errors end loading
states, and shutdown blocks late publication and bounds cleanup work.

## Installation and verification

`./install.sh --dev` prepares a local development environment and preserves an
existing global launcher. A pipx installation is separate from that environment.
The published package version is 1.0.4; local pre-release build identifiers in
older audit records are historical.

[TESTING.md](TESTING.md) describes the current commands and quality gates.
[VALIDATION.md](VALIDATION.md) records the published release checks.
[STABILITY.md](STABILITY.md) retains the detailed audit and earlier build results.
