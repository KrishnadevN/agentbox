#!/usr/bin/env bash
# agentbox-install-texlive.sh [--scheme full|medium|small] [--update]
#
# Installs TeX Live from TUG (official installer) into /usr/local/texlive/<year>.
# The same install serves the host AND the "docs" containers (mounted read-only),
# so there is one copy on disk. TUG binaries run on Arch and on Ubuntu 24.04.
#   --update   update an existing install instead (tlmgr update --self --all)
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/../lib/common.sh"
SCHEME=full UPDATE=0
while (($#)); do
  case $1 in --scheme) SCHEME=${2:?}; shift ;; --update) UPDATE=1 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; *) ab_die "unknown option $1" ;; esac; shift
done

latest() { find /usr/local/texlive -maxdepth 1 -name '20[0-9][0-9]' -type d 2>/dev/null | sort | tail -1; }

if ((UPDATE)); then
  t=$(latest); [[ -n $t ]] || ab_die "no TeX Live in /usr/local/texlive"
  ab_section "Updating $t"
  sudo "$t/bin/x86_64-linux/tlmgr" update --self --all
  exit 0
fi

ab_section "Pre-checks"
pacman -Qq texlive-basic >/dev/null 2>&1 && ab_warn "Arch texlive packages are installed. Remove them first to avoid PATH conflicts: sudo pacman -Rns \$(pacman -Qqs '^texlive-')"
[[ -n $(latest) ]] && ab_die "TeX Live already at $(latest). Use --update."
command -v perl >/dev/null || sudo pacman -S --needed --noconfirm perl
ab_ok "ready (scheme: $SCHEME; full needs about 8 GB and 20-60 min)"

ab_section "Download and verify installer"
tmp=$(mktemp -d); cd "$tmp"
base=https://mirror.ctan.org/systems/texlive/tlnet
curl -fsSL -O "$base/install-tl-unx.tar.gz" -O "$base/install-tl-unx.tar.gz.sha512"
sha512sum -c install-tl-unx.tar.gz.sha512 && ab_ok "checksum OK"
tar xzf install-tl-unx.tar.gz

ab_section "Install (as root: files are root-owned, so nothing else can change them)"
sudo perl ./install-tl-*/install-tl --no-interaction --scheme="$SCHEME" --paper=a4
cd /; rm -rf "$tmp"

t=$(latest)
ab_ok "installed: $t"
cat <<EOF

Next:
  1. In $AB_CONFIG/hosts/$(ab_hostname).toml set:   tex_root = "$t"
  2. Open a new terminal (the shell integration adds TeX to PATH), then: tex --version
  3. Never compile agent-written .tex files on the host with -shell-escape.
EOF
