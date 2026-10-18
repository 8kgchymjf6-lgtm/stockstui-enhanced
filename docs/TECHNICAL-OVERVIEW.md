# Technical overview — stocksTUI Enhanced

Updated: 2026-10-18. Upstream base: `v0.1.0-b14`.
Local maintenance branch: `fix/stability`.
Package version: `0.1.0b14+enhanced.20261018.1`.

This is a local fork of `andriy-git/stocksTUI`. Earlier formatting and sorting
improvements are retained alongside the completed stability audit. The changes
now span providers, persistence, configuration validation, views and tests;
the old description limiting modifications to three Python files is obsolete.

## Responsibilities

- `main.py`: application lifecycle, workers, request generations, table updates,
  search/sort coordination and view transitions.
- `quote_status.py` and `quote_time.py`: pure status formatting and timestamp
  interpretation. The compact Last Refresh line is preserved.
- `config_manager.py`, `config_validation.py`: atomic configuration persistence,
  process locking, merges, validation, backups and protected recovery sessions.
- `database.py` and data providers: persistent snapshots, synchronization,
  retrieval, normalization and provider-specific failure handling.
- `presentation/formatter.py`: financial display values and table formatting.
- `ui/`: views, modals and charts; asynchronous actions are awaited and option
  callbacks retain the original instrument context.
- `tests/`: normal functionality, failures, races, temporary-file recovery,
  script exit statuses and installer launcher preservation.

The default development installer uses a local environment. The user's regular
launcher remains `~/.local/bin/stockstui` in the pipx environment
`~/.local/share/pipx/venvs/stockstui`. Updating that installation uses a tested
wheel without changing runtime dependencies. The local version distinguishes
it from upstream; a new public tag or release is not required for local use.

See [STABILITY.md](STABILITY.md) for completed audit areas, current quality gates,
reproduction commands and limits. Historical validation documents describe
previous builds and should not override that current status.
