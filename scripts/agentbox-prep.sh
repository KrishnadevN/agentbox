#!/usr/bin/env bash
# agentbox-prep.sh — prepare a Linux host for agentbox (Arch-based today). Safe to re-run.
#
#   ~/.agentbox/scripts/agentbox-prep.sh [--dry-run] [--if-supported] [--update-runsc] [--gvisor RELEASE] [--extras]
#
#   --if-supported  on a host this script does not support yet, print a warning and
#                   exit 0 instead of failing (for dotfile managers such as chezmoi)
#   --dry-run       print what would change, change nothing
#   --update-runsc  reinstall gVisor even if present (RELEASE default: latest)
#   --extras        also install compsize (shows btrfs reflink sharing in the checks)
#
# Asks for sudo only for: packages, subuid/subgid, cgroup drop-in, linger, oomd, runsc.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/../lib/common.sh"

DRY=0 UPD_RUNSC=0 GVISOR=latest EXTRAS=0 IFSUP=0
while (($#)); do
  case $1 in
    --dry-run) DRY=1 ;;
    --if-supported) IFSUP=1 ;;
    --update-runsc) UPD_RUNSC=1 ;;
    --gvisor) GVISOR=${2:?release}; shift ;;
    --extras) EXTRAS=1 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) ab_die "unknown option $1" ;;
  esac
  shift
done
run() { if ((DRY)); then printf '   [dry-run] %s\n' "$*"; else "$@"; fi; }
HOSTN=$(ab_hostname); HOSTF=$AB_CONFIG/hosts/$HOSTN.toml

ab_section "0. Basic checks"
[[ $EUID -ne 0 ]] || ab_die "run as your normal user, not root (sudo is used where needed)"
[[ -f $AB_ROOT/defaults.toml ]] || ab_die "$AB_ROOT is not the agentbox repo (defaults.toml missing)"
# Supported hosts. Add new ones here (package names and install command differ).
osname=$( (. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown}") )
if [[ $(uname -s) != Linux ]]; then
  supported=0
elif command -v pacman >/dev/null; then
  supported=1
else
  supported=0
fi
if ((!supported)); then
  msg="host '$osname' is not supported by this script yet (supported: Arch-based Linux)."
  msg+=" Install podman, passt, nftables, python3, git, tmux, curl, zstd and gVisor by hand, then read the steps below in this script."
  if ((IFSUP)); then ab_warn "$msg"; exit 0; fi
  ab_die "$msg"
fi
ab_ok "supported host: $osname ('$HOSTN'), user $USER"

ab_section "1. Host packages (only what the HOST needs)"
# podman pulls in crun, netavark, aardvark-dns, conmon. passt provides pasta.
# nftables: we load egress rules into each pod's netns from the host.
# python: config merging (tomllib). tmux: sessions that survive disconnects.
# zstd: unpack the gVisor release. Everything else lives inside the images.
pkgs=(podman passt nftables tmux git python curl zstd)
((EXTRAS)) && pkgs+=(compsize)
missing=(); for p in "${pkgs[@]}"; do pacman -Qq "$p" >/dev/null 2>&1 || missing+=("$p"); done
if ((${#missing[@]})); then
  ab_step "installing: ${missing[*]}"; run sudo pacman -S --needed --noconfirm "${missing[@]}"
fi
ab_ok "packages present: ${pkgs[*]}"
pacman -Qq gvisor-bin >/dev/null 2>&1 && ab_warn "AUR gvisor-bin is installed: remove it (sudo pacman -Rns gvisor-bin); it is outdated and conflicts"
if pacman -Qq texlive-basic >/dev/null 2>&1; then
  ab_warn "Arch texlive-* packages found: these cannot be shared with the containers. See scripts/agentbox-install-texlive.sh"
fi

ab_section "2. User namespaces (subuid/subgid)"
if grep -q "^$USER:" /etc/subuid && grep -q "^$USER:" /etc/subgid; then
  ab_ok "subuid/subgid ranges exist"
else
  ab_step "adding 65536 sub-IDs for $USER"
  run sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$USER"
  run podman system migrate
  ab_ok "subuid/subgid added"
fi
[[ $(cat /proc/sys/kernel/unprivileged_userns_clone 2>/dev/null || echo 1) == 1 ]] \
  && ab_ok "unprivileged user namespaces enabled" || ab_die "kernel.unprivileged_userns_clone=0: enable it"

ab_section "3. cgroup v2 delegation (needed for CPU caps)"
[[ $(stat -fc %T /sys/fs/cgroup) == cgroup2fs ]] || ab_die "cgroup v2 not active"
ctrl=/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers
have=$(cat "$ctrl" 2>/dev/null || true)
if [[ " $have " == *" cpu "* && " $have " == *" memory "* && " $have " == *" pids "* ]]; then
  ab_ok "delegated controllers: $have"
else
  ab_step "adding /etc/systemd/system/user@.service.d/delegate.conf"
  run sudo mkdir -p /etc/systemd/system/user@.service.d
  if ((!DRY)); then
    printf '[Service]\nDelegate=cpu cpuset io memory pids\n' | sudo tee /etc/systemd/system/user@.service.d/delegate.conf >/dev/null
  fi
  run sudo systemctl daemon-reload
  ab_warn "delegation changed: LOG OUT completely and back in (or reboot), then re-run this script"
fi

ab_section "4. Session persistence (linger)"
want=$(ab_toml_get "$HOSTF" host.linger false)
cur=$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo no)
if [[ $want == true && $cur != yes ]]; then run sudo loginctl enable-linger "$USER"; ab_ok "linger enabled"
elif [[ $want != true ]]; then ab_info "linger=$cur (hosts file says linger=$want; laptop: pods stop when you log out — fine)"
else ab_ok "linger already enabled"; fi

ab_section "5. OOM handling (systemd-oomd)"
if systemctl is-active -q systemd-oomd; then ab_ok "systemd-oomd active"
elif systemctl list-unit-files systemd-oomd.service >/dev/null 2>&1; then
  run sudo systemctl enable --now systemd-oomd; ab_ok "systemd-oomd enabled"
else ab_warn "systemd-oomd not available; the hard MemoryMax still protects the host"; fi

ab_section "6. gVisor (runsc) from the official release"
install_runsc() {
  local tmp url arch; arch=$(uname -m); tmp=$(mktemp -d)
  url=https://storage.googleapis.com/gvisor/releases/release/$GVISOR/$arch
  ab_step "downloading gVisor release '$GVISOR' ($arch) into $tmp"
  if curl -fsSL -o "$tmp/gvisor.tar.zstd" "$url/gvisor.tar.zstd" \
     && curl -fsSL -o "$tmp/gvisor.tar.zstd.sha512" "$url/gvisor.tar.zstd.sha512"; then
    (cd "$tmp" && sha512sum -c --quiet gvisor.tar.zstd.sha512) || ab_die "checksum mismatch"
    mkdir "$tmp/x"; tar --zstd -xf "$tmp/gvisor.tar.zstd" -C "$tmp/x"
  else
    ab_warn "new-style tarball not found; trying legacy single-binary layout"
    mkdir "$tmp/x"
    curl -fsSL -o "$tmp/x/runsc" "$url/runsc" && curl -fsSL -o "$tmp/runsc.sha512" "$url/runsc.sha512" \
      || ab_die "gVisor download failed (check https://gvisor.dev/docs/user_guide/install/)"
    (cd "$tmp/x" && sed 's#  .*#  runsc#' ../runsc.sha512 | sha512sum -c --quiet) || ab_die "checksum mismatch"
  fi
  local bin; bin=$(find "$tmp/x" -type f -name runsc | head -1)
  [[ -n $bin ]] || ab_die "runsc not found in the release"
  run sudo install -m 0755 "$bin" /usr/local/bin/runsc
  local side; side=$(find "$tmp/x" -type d -name gvisor-bin | head -1)
  if [[ -n $side ]]; then
    run sudo rm -rf /usr/local/bin/gvisor-bin
    run sudo cp -a "$side" /usr/local/bin/gvisor-bin
    run sudo chmod -R a+rX,go-w /usr/local/bin/gvisor-bin
  fi
  rm -rf "$tmp"
}
if [[ -x /usr/local/bin/runsc && $UPD_RUNSC == 0 ]]; then
  ab_ok "runsc present: $(/usr/local/bin/runsc --version | head -1) (use --update-runsc to update)"
else
  install_runsc
  ((DRY)) || ab_ok "installed: $(/usr/local/bin/runsc --version | head -1)"
fi
[[ -d /usr/local/bin/gvisor-bin ]] && ab_ok "gvisor-bin/ sidecar present" \
  || ab_info "no gvisor-bin/ sidecar (normal for older releases)"

ab_section "7. Podman configuration"
d=$HOME/.config/containers/containers.conf.d
run mkdir -p "$d"
run ln -sfn "$AB_ROOT/config/containers.conf.d/99-agentbox.conf" "$d/99-agentbox.conf"
ab_ok "runsc registered via $d/99-agentbox.conf (default runtime stays crun)"
bad=$(grep -rniE 'map-gw|map-host-loopback|allow_host_loopback' /usr/share/containers /etc/containers \
      "$HOME/.config/containers" 2>/dev/null | grep -v '^\s*#' || true)
[[ -z $bad ]] && ab_ok "no host-loopback mapping in containers.conf" || { ab_fail "host loopback exposed:"; echo "$bad"; }
[[ $(podman info --format '{{.Store.GraphDriverName}}' 2>/dev/null) == overlay ]] \
  && ab_ok "storage driver: overlay" || ab_warn "storage driver is not overlay"

ab_section "8. Folders"
run mkdir -p "$AB_PROJECTS" "$AB_AGENTS" \
  "$AB_STATE"/{tools/{bin,npm},auth,home,ctx,bridge,cache/{uv,pnpm,npm},logs}
run chmod 700 "$AB_STATE" "$AB_STATE/auth" "$AB_AGENTS"   # auth/: token files (copilot.env)
fs=$(findmnt -no FSTYPE -T "$AB_STATE"); fs2=$(findmnt -no FSTYPE -T "$AB_AGENTS")
ab_ok "folders ready ($AB_STATE on $fs, $AB_AGENTS on $fs2)"
[[ $fs == btrfs && $fs2 == btrfs ]] || ab_info "not btrfs: uv falls back to copying (works, uses more disk)"

ab_section "9. Your config ($AB_CONFIG)"
run mkdir -p "$AB_CONFIG/hosts" "$AB_CONFIG/projects"
if [[ ! -e $AB_CONFIG/config.toml ]] && ((!DRY)); then
  cp "$AB_ROOT/examples/config.toml" "$AB_CONFIG/config.toml"; ab_ok "created $AB_CONFIG/config.toml (all commented out)"
fi
if [[ -f $HOSTF ]]; then
  ab_ok "exists (label=$(ab_toml_get "$HOSTF" host.label "?"))"
else
  gpu=none; command -v nvidia-smi >/dev/null && gpu=nvidia-cdi
  ((DRY)) || sed -e "s/^label .*/label    = \"$HOSTN\"           # shown to agents/" \
                 -e "s/^gpu .*/gpu      = \"$gpu\"/" "$AB_ROOT/examples/hosts/HOSTNAME.toml" > "$HOSTF"
  ab_ok "created $HOSTF — edit 'label' (e.g. laptop)"
fi

ab_section "10. Agent context ($AB_CONTEXT)"
run mkdir -p "$AB_CONTEXT/instructions" "$AB_CONTEXT/skills" "$AB_CONTEXT/projects" "$AB_CONTEXT/agents"
ab_ok "instructions/, skills/ and projects/ ready (make it a private git repo if you want to sync it)"

ab_section "11. Shell integration and permissions"
run chmod +x "$AB_ROOT"/bin/* "$AB_ROOT"/scripts/*.sh
# fish reads conf.d by itself, so a link is enough. bash/zsh rc files are often
# managed by dotfile tools, so this script never edits them: it tells you the line.
if [[ -d $HOME/.config/fish ]] || command -v fish >/dev/null; then
  run mkdir -p "$HOME/.config/fish/conf.d"
  run ln -sfn "$AB_ROOT/shell/agentbox.fish" "$HOME/.config/fish/conf.d/agentbox.fish"
  ab_ok "fish: PATH, completion and git guard linked (open a new terminal)"
fi
for sh in bash zsh; do
  rc=$HOME/.${sh}rc
  command -v "$sh" >/dev/null || continue
  if grep -qs "shell/agentbox.$sh" "$rc"; then ab_ok "$sh: $rc sources agentbox.$sh"
  else
    note=""; [[ $sh == zsh ]] && note=" (after compinit)"
    ab_info "$sh: add to $rc$note:  source $AB_ROOT/shell/agentbox.$sh"
  fi
done

ab_section "Done"
cat <<EOF
Next steps:
  1. agentbox-build                 # build images (~10-20 min first time)
  2. agentbox-update-tools          # install Claude Code, Codex, Antigravity CLIs
  3. (LaTeX) $AB_ROOT/scripts/agentbox-install-texlive.sh
  4. $AB_ROOT/scripts/agentbox-check.sh   # full PASS/FAIL test suite
EOF
