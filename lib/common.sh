# shellcheck shell=bash
# agentbox: shared helpers. Source this file; do not run it.

# Code (this repo) and YOUR config are kept apart, so the package can be shared.
AB_ROOT=${AB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}   # the agentbox package
AB_LIB=$AB_ROOT/lib
AB_CONFIG=${AB_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/agentbox}  # your config.toml, hosts/, projects/
AB_STATE=${AB_STATE:-$HOME/.local/share/agentbox}      # tokens, tools, caches, logs (never in Git)
# Folder locations: change them with environment variables (fish: set -Ux AB_PROJECTS ~/code;
# bash/zsh: export AB_PROJECTS=~/code in the rc file)
AB_PROJECTS=${AB_PROJECTS:-$HOME/Projects}             # YOUR repos (trusted)
AB_AGENTS=${AB_AGENTS:-$HOME/.agents-projects}         # agent copies (untrusted)
AB_CONTEXT=${AB_CONTEXT:-$HOME/.agents-context}        # instructions, skills, private project files
export AB_ROOT AB_LIB AB_CONFIG AB_STATE AB_PROJECTS AB_AGENTS AB_CONTEXT

if [[ -t 1 ]]; then
  _G=$'\e[32m' _R=$'\e[31m' _Y=$'\e[33m' _B=$'\e[1;34m' _D=$'\e[2m' _N=$'\e[0m'
else
  _G='' _R='' _Y='' _B='' _D='' _N=''
fi

ab_section() { printf '\n%s== %s ==%s\n' "$_B" "$*" "$_N"; }
ab_step()    { printf '%s-> %s%s\n' "$_D" "$*" "$_N"; }
ab_ok()      { printf '%sPASS%s: %s\n' "$_G" "$_N" "$*"; }
ab_fail()    { printf '%sFAIL%s: %s\n' "$_R" "$_N" "$*"; }
ab_warn()    { printf '%sWARN%s: %s\n' "$_Y" "$_N" "$*" >&2; }
ab_info()    { printf 'INFO: %s\n' "$*"; }
ab_die()     { printf '%sERROR%s: %s\n' "$_R" "$_N" "$*" >&2; exit 1; }

ab_hostname() { uname -n | cut -d. -f1; }

# Slice names: "-" means "child of" in systemd, so normalise project names.
ab_norm() { printf '%s' "$1" | tr -c 'A-Za-z0-9_' '_'; }

# ab_toml_get FILE dotted.key DEFAULT   -> prints value (lists joined by space)
ab_toml_get() {
  python3 - "$1" "$2" "${3-}" <<'PY'
import sys, tomllib
f, key, default = sys.argv[1:4]
try:
    with open(f, "rb") as fh: d = tomllib.load(fh)
    for k in key.split("."): d = d[k]
except Exception:
    print(default); sys.exit(0)
if isinstance(d, bool): d = str(d).lower()
print(" ".join(map(str, d)) if isinstance(d, list) else d)
PY
}

# Run a command inside a transient systemd user scope in the given slice.
# conmon / pasta / runsc started by this command stay in the slice, which is
# what enforces the memory/CPU caps (rootless runsc ignores podman's limits).
ab_scoped() {
  local slice=$1 unit=$2; shift 2
  systemd-run --user --scope --quiet -p Delegate=yes \
    --slice="$slice" --unit="${unit}-$(date +%s%N | tail -c 7)" -- "$@"
}

# ab_safe_mkdir BASE REL...  create folders inside an agent-writable BASE without
# following symlinks (see lib/safe_mkdir.py)
ab_safe_mkdir() { python3 "$AB_LIB/safe_mkdir.py" "$@"; }

# ab_pod_netns <pod>  -> path of the pod's network namespace (empty if none)
ab_pod_netns() {
  local infra
  infra=$(podman pod inspect -f '{{.InfraContainerID}}' "$1" 2>/dev/null) || return 0
  podman inspect -f '{{.NetworkSettings.SandboxKey}}' "$infra" 2>/dev/null || true
}

ab_require_cmds() {
  local c miss=()
  for c in "$@"; do command -v "$c" >/dev/null 2>&1 || miss+=("$c"); done
  ((${#miss[@]} == 0)) || ab_die "missing commands: ${miss[*]} (run ~/.agentbox/scripts/agentbox-prep.sh)"
}
