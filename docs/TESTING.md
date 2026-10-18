# Testing — stocksTUI Enhanced

Updated: 2026-10-18. Release baseline: **v1.0.4-enhanced / package 1.0.4**.

## Prepare a development environment

From the repository root, with Python 3.10 or newer:

```bash
./install.sh --dev
```

The installer prefers an existing `.venv`, then `venv`, otherwise creates
`.venv`. Commands below assume `.venv`; substitute `venv` if that was selected.
It does not replace an existing pipx/global launcher by default.

For the recorded Linux/Python 3.14 environment, the constraints file can be used
with an already activated development environment:

```bash
python -m pip install -c requirements/validated-linux-py314.txt -e '.[dev]'
```

These constraints record the validated environment, not a portable lockfile for
all operating systems or Python versions. CI resolves the project dependencies
separately on each supported Python version.

## Run the release checks

```bash
./run_tests.sh
.venv/bin/python -m mypy stockstui
.venv/bin/python -m ruff check stockstui tests --select=E9,F63,F7,F82
bash -n install.sh run_tests.sh
git diff --check
```

`run_tests.sh` discovers the complete unittest suite, measures statement and
branch coverage, and enforces the **80% combined coverage threshold** from
`pyproject.toml`. Test or coverage failures return a nonzero status. The script
sets temporary XDG configuration, cache and data directories plus temporary
Hypothesis storage, and does not install or upgrade dependencies.

To select the interpreter explicitly:

```bash
STOCKSTUI_PYTHON=/path/to/python ./run_tests.sh
```

`./run_tests.sh --no-coverage` is available for diagnostics; it does not satisfy
the release coverage gate. The Ruff check above is the critical syntax/undefined
name check, not an assertion that every optional style rule passes.

## Targeted and live tests

For a focused regression check:

```bash
.venv/bin/python -m unittest -v tests.test_parser tests.test_quote_time
```

Live API checks are skipped by default. To include them in the full isolated
runner, explicitly opt in:

```bash
RUN_LIVE_TESTS=1 ./run_tests.sh
```

This makes real provider requests and depends on network access, provider uptime
and rate limits. A live failure needs investigation; it is not automatically a
local application defect. Normal tests use synthetic data and mocked providers.

## Verified release baseline

- Local Linux/Python 3.14: **924 tests, 922 passed, 2 optional live checks skipped**.
- Combined statement/branch coverage: **92.31%**; `stockstui/main.py`: **84.48%**.
- **118 regression tests** passed against the installed 1.0.4 production package.
- [Release CI](https://github.com/8kgchymjf6-lgtm/stockstui-enhanced/actions/runs/39138313029)
  passed on **Python 3.10, 3.11, 3.12, 3.13 and 3.14**. Each job ran the complete
  924-test suite with the two expected skips and enforced the coverage threshold,
  full-package mypy and critical Ruff checks.

These numbers describe the release baseline, not every future commit or
platform. Tests and coverage do not establish that a program has no defects.
See [VALIDATION.md](VALIDATION.md) for release provenance and limitations, and
[STABILITY.md](STABILITY.md) for the detailed audit history.
