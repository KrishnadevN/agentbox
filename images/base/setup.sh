#!/usr/bin/env bash
# Base layer setup (runs as root, bash -e).
userdel -r ubuntu 2>/dev/null || true

# Node LTS from nodejs.org (Codex CLI launcher, web projects). Rebuild for updates.
NODE_MAJOR=24
V=$(curl -fsSL https://nodejs.org/dist/index.json | python3 -c \
  "import json,sys;print(next(r['version'] for r in json.load(sys.stdin) if r['version'].startswith('v$NODE_MAJOR.')))")
curl -fsSL "https://nodejs.org/dist/$V/node-$V-linux-x64.tar.xz" | tar -xJ -C /usr/local --strip-components=1

# ImageMagick: Ubuntu caps the pixel cache at 1 GiB RAM / 2 GiB disk; large scans or
# multi-page PDFs fail. Raise the caps (the sandbox RAM cap still applies). The coder
# line re-allows PDF/PS if a future Ubuntu update blocks them again.
P=/etc/ImageMagick-6/policy.xml
sed -i -E 's#<policy domain="coder" rights="none" pattern="(PDF|PS|PS2|PS3|EPS|XPS)" />#<policy domain="coder" rights="read|write" pattern="\1" />#' "$P"
sed -i -E 's#(name="memory" value=)"[^"]*"#\1"4GiB"#; s#(name="map" value=)"[^"]*"#\1"8GiB"#; s#(name="disk" value=)"[^"]*"#\1"16GiB"#; s#(name="width" value=)"[^"]*"#\1"64KP"#; s#(name="height" value=)"[^"]*"#\1"64KP"#; s#(name="area" value=)"[^"]*"#\1"1GP"#' "$P"

chmod 755 /usr/local/bin/magick

ln -sf /usr/bin/fdfind /usr/local/bin/fd
mkdir -p /work /upstream /data /ref /home/agent /etc/agentbox /opt/agentbox/tools
# Shared agent defaults (~/.agents-context/agents/<agent>/) are mounted here; Codex reads
# its system config through the link (dangling = no shared config).
mkdir -p /etc/agentbox/defaults /etc/codex
ln -sfn /etc/agentbox/defaults/config.toml /etc/codex/config.toml
chmod 1777 /home/agent
