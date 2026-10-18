#!/usr/bin/env bash
# Development installer; an existing global command is never replaced implicitly.
set -euo pipefail
PROJECT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
venv_dir=""
bin_dir="$HOME/.local/bin"
link_command=false
replace_launcher=false
offline=false
no_deps=false
dev=false
while (( $# )); do
  case "$1" in
    --venv|--bin-dir)
      if (( $# < 2 )) || [[ -z "$2" ]]; then echo "$1 requires a path" >&2; exit 2; fi
      if [[ "$1" == --venv ]]; then venv_dir="$2"; else bin_dir="$2"; fi
      shift 2 ;;
    --link) link_command=true; shift ;;
    --replace-launcher) link_command=true; replace_launcher=true; shift ;;
    --offline) offline=true; shift ;;
    --no-deps) no_deps=true; shift ;;
    --dev) dev=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--venv PATH] [--dev] [--no-deps] [--offline] [--link [--bin-dir PATH]] [--replace-launcher]"
      echo "Default: install locally; keep any existing stockstui command."
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ -z "$venv_dir" ]]; then
  if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then venv_dir="$PROJECT_DIR/.venv"
  elif [[ -x "$PROJECT_DIR/venv/bin/python" ]]; then venv_dir="$PROJECT_DIR/venv"
  else venv_dir="$PROJECT_DIR/.venv"; fi
fi
[[ "$venv_dir" == /* ]] || venv_dir="$PWD/$venv_dir"
[[ "$bin_dir" == /* ]] || bin_dir="$PWD/$bin_dir"
launcher="$bin_dir/stockstui"
local_executable="$venv_dir/bin/stockstui"
check_launcher() {
if [[ -e "$launcher" || -L "$launcher" ]]; then
  if [[ ! -L "$launcher" ]]; then
    echo "Refusing to overwrite a regular file or directory: $launcher" >&2; exit 1
  fi
  if [[ "$(readlink -- "$launcher")" != "$local_executable" && "$replace_launcher" != true ]]; then
    echo "Existing launcher retained: $launcher. Use --replace-launcher to replace this symlink explicitly." >&2; exit 1
  fi
fi
}
if [[ "$link_command" == true ]]; then check_launcher; fi
if [[ ! -x "$venv_dir/bin/python" ]]; then
  "${STOCKSTUI_PYTHON:-python3}" -m venv "$venv_dir"
fi
venv_python="$venv_dir/bin/python"
if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
  "$venv_python" -m ensurepip
fi
pip_args=(install -e)
project_spec="$PROJECT_DIR"
[[ "$dev" == false ]] || project_spec="$PROJECT_DIR[dev]"
pip_args+=("$project_spec")
[[ "$no_deps" == false ]] || pip_args+=(--no-deps)
[[ "$offline" == false ]] || pip_args+=(--no-index --no-build-isolation)
"$venv_python" -m pip "${pip_args[@]}"
if [[ ! -x "$local_executable" ]]; then echo "Installation did not create $local_executable" >&2; exit 1; fi
if [[ "$link_command" == true ]]; then
  mkdir -p -- "$bin_dir"
  # Construct first, replace atomically only after a successful installation.
  link_tmp=$(mktemp -d "$bin_dir/.stockstui-link.XXXXXX")
  trap 'rm -rf -- "$link_tmp"' EXIT
  ln -s -- "$local_executable" "$link_tmp/stockstui"
  check_launcher
  mv -Tf -- "$link_tmp/stockstui" "$launcher"
  echo "Command: $launcher"
fi
echo "Installed: $local_executable"
