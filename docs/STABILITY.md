# Local stability work: prices and watchlists

Date: 2026-10-18. Branch: `fix/stability`. This is a local enhanced build;
package metadata remains `0.1.0b14`. There is no new public release.

## Behavior changed

- JSON saves use unique temporary files, file synchronization, an interprocess
  lock with a bounded wait and atomic replacement. A three-way merge preserves independent changes
  from different windows, including watchlist order. Conflicting edits are
  rejected with an explicit error rather than overwriting another window.
- Failed saves restore committed in-memory configuration. UI actions and modal
  callbacks report failure and stop before reporting success. Option position
  writes/deletes also return failure so their UI state only changes on success.
- Providers publish cache entries under a short lock. Persistence and readers
  receive independent snapshots; network calls do not hold that lock. Shutdown
  stops new publications to the UI, cancels workers, saves snapshots and closes
  SQLite in a finally block even if an optional cache save fails.
- Independent background tasks have separate Textual worker groups. Price
  requests carry a generation id, so queued results from superseded requests do
  not replace current UI data. Price provider requests are serialized to prevent
  a cancelled thread from overwriting the cache after a newer fetch completes.
- Search snapshots are replaced after every price redraw. Active search and
  sorting apply to current values; clearing search restores current full rows.
- Successful fetch timestamps accompany cached price data and survive database
  persistence. Failed retrievals retain old prices with an explicit cached or
  unverified status. The status bar uses acquisition timestamps instead of the
  time a UI message arrived; its tooltip contains the full status.
- Failed price workers and cancelled current workers end the loading state.
  A later refresh can recover without restarting.
- Refresh intervals must be finite and at least one second. Both input
  validation and timer startup enforce this.
- Tag button ids are independent of unsafe label characters, and tag selection
  preserves the original tag. Labels are rendered as plain text.

The previously installed SQLite connection lock and `BEGIN IMMEDIATE` changes
are retained in their own commit, with their concurrency regression tests.

## Validation

The existing unittest suite is retained. `tests/test_stability.py` adds
26 regression tests using temporary files and synthetic data. Test fixture
updates use real price messages and dictionaries, avoid module reloads that
invalidate exception identities, and require save failures to be observable.
The exact executed results are recorded in the task's installation report.

The additional stress scenario uses 1,000 symbols, 50 complete refreshes,
50,000 rendered rows, ten search/refresh cycles, 40 tab changes and 51 rapid
price requests. Four independent processes perform 200 JSON saves and verify
that all final changes survive in a parseable file. No personal portfolio or
watchlist data is used by these tests.

## Deferred work

The broad audit still has follow-up items: structural validation and recovery
for malformed configuration files; late historical/options responses;
partial options payloads; options failure loading state; ticker suggestion
formatting; and FRED leap-day calculations. The current changes focus on
price/watchlist workflows. Broader CI gates, installer cleanup and larger
refactoring remain maintenance follow-ups.

## Installation and recovery

Build and install a wheel with `--no-deps` into the existing pipx environment
only after validation. This keeps the previously selected runtime versions.
Existing processes use their already imported code; restart stocksTUI to use
the complete local build.

Before this change, source, tests and personal JSON configuration were archived
in `stockstui-foer-stabilitetsrettelser-20261018.tar.gz` in the task outputs.
The earlier full pipx backup is also retained there. Do not restore an old
configuration over newer personal edits without comparing them first.
