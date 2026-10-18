#!/usr/bin/env bash
# Run from any directory, without installing or upgrading packages.
set -euo pipefail
PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case "${1:-}" in
  "") with_coverage=true ;;
  --no-coverage) with_coverage=false; shift ;;
  -h|--help) echo "Usage: $0 [--no-coverage] (optional STOCKSTUI_PYTHON=/path/to/python)"; exit 0 ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac
if (( $# )); then echo "Unexpected arguments: $*" >&2; exit 2; fi
if [[ -n "${STOCKSTUI_PYTHON:-}" ]]; then
  test_python="$STOCKSTUI_PYTHON"
elif [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  test_python="$PROJECT_DIR/.venv/bin/python"
elif [[ -x "$PROJECT_DIR/venv/bin/python" ]]; then
  test_python="$PROJECT_DIR/venv/bin/python"
else
  test_python=$(command -v python3)
fi
cd -- "$PROJECT_DIR"
test_tmp=$(mktemp -d "${TMPDIR:-/tmp}/stockstui-tests.XXXXXX")
trap 'rm -rf -- "$test_tmp"' EXIT
export XDG_CONFIG_HOME="$test_tmp/config"
export XDG_CACHE_HOME="$test_tmp/cache"
export XDG_DATA_HOME="$test_tmp/data"
export HYPOTHESIS_STORAGE_DIRECTORY="$test_tmp/hypothesis"
if [[ "$with_coverage" == false ]]; then
  "$test_python" -m unittest discover -s tests -t . -p 'test_*.py' -v
else
  if ! "$test_python" -m coverage --version >/dev/null 2>&1; then
    echo "Coverage is required. Install the dev dependencies, or explicitly use --no-coverage." >&2
    exit 2
  fi
  "$test_python" -m coverage run -m unittest discover -s tests -t . -p 'test_*.py' -v
  # The threshold comes from pyproject.toml. Its nonzero status must reach CI.
  "$test_python" -m coverage report
fi
echo "All requested test checks passed."
