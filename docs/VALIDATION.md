# Release validation — stocksTUI Enhanced 1.0.4

Validated and published: **2026-10-18**.

## Release identity

- [Published release and assets](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/releases/tag/v1.0.4-enhanced):
  **stocksTUI Enhanced v1.0.4**, package version **1.0.4**.
- Annotated tag: `v1.0.4-enhanced`.
- Tagged source commit: `1c86bf021753f28a221d1bc054b9c168239030ce`.
- Upstream base: `v0.1.0-b14`; previous enhanced release: `v1.0.3-enhanced`.
- Assets: `stockstui-1.0.4-py3-none-any.whl` and `SHA256SUMS.txt`.

The release promotes the measured local build
`0.1.0b14+enhanced.20261018.4`. Production Python files and package resources at
the release tag match that build. Release preparation changes package metadata
and documentation, plus one test timestamp assertion for Python 3.10
compatibility; the expected UTC instant remains unchanged.

Later documentation corrections on `main` do not move the published tag or
replace its wheel. In particular, the corrected source user manual on `main`
may be newer than the `--man` text bundled in the frozen 1.0.4 release.

## Automated checks

The complete local suite ran **924 tests: 922 passed and 2 opt-in live API checks
skipped** on Linux/Python 3.14. Combined statement/branch coverage was **92.31%**,
above the **80%** gate; `stockstui/main.py` measured **84.48%**. The local combined
measurement includes all test modules across four isolated processes.

Full-package mypy checked **49 source files**. Critical Ruff
(`E9,F63,F7,F82`), shell syntax, Git whitespace and dependency checks passed.

[GitHub Actions run 39138313029](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/actions/runs/39138313029)
passed on the tagged commit for **Python 3.10, 3.11, 3.12, 3.13 and 3.14** on
Linux. Every job ran the complete **924-test suite** with the two expected live
skips and enforced coverage, mypy and critical Ruff checks. The first candidate
CI exposed a Python 3.10-only test timestamp parsing issue; the assertion was
made portable and the entire five-version matrix then passed.

## Installed package and artifact integrity

After installing 1.0.4 in the existing pipx environment:

- **118 regression tests** passed against the actual installed production modules
  with isolated validation tools.
- All **55 Python/resource files**, including **49 Python files**, matched the
  release wheel and source at the release tag.
- All **40 other installed distribution versions**, the launcher and the hashes
  of the four personal JSON configuration files remained unchanged.
- Package metadata and `stockstui --version` identified version **1.0.4**.
- The published wheel was downloaded back from GitHub and compared byte-for-byte
  with the local validated artifact and its SHA-256 checksum.

Published wheel SHA-256:

```text
c561d327195d73802e8ca9c1b8a22052399474b42beefa15df81dc3e2a6a006e
```

Source backups, prior wheels and the validation log archive were retained
separately from the repository. Personal settings and credentials are not
published as release artifacts.

## Scope and limits

The changes cover quote/cache integrity, atomic configuration and watchlist
operations, request cancellation and stale responses, search/filter/sort,
keyboard navigation, options, FRED, chart boundaries and shutdown/error paths.
See the [full enhanced changelog](CHANGELOG-ENHANCED.md#v104-enhanced) for changes
since 1.0.3 and [STABILITY.md](STABILITY.md) for the detailed audit.

The two live checks were intentionally skipped in release validation. These
results do not guarantee external provider uptime, correctness of every market
value, or absence of every possible bug. This release's CI evidence covers
Linux; macOS and Windows/WSL were not validated in that matrix. Coverage is not a
percentage guarantee of reliability. Mutation testing is not claimed.

Reproduction commands are in [TESTING.md](TESTING.md). Installation, backup and
release procedures are in [MAINTENANCE.md](MAINTENANCE.md). The original 1.0.0
validation record remains available in the
[historical validation document](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/blob/8f1dbe87d9c1e94b0f0d6054c45e5743d0409a9e/docs/VALIDATION.md).
