#!/usr/bin/env bash
# agentbox-check.sh — PASS/FAIL test suite for the sandbox. Safe to re-run.
#
#   ~/.agentbox/scripts/agentbox-check.sh [--runtime runsc|crun] [--keep] [--quick] [--destructive]
#
#   --runtime      test agent containers with this runtime (default runsc)
#   --keep         keep the self-test pod and folders afterwards (to poke around);
#                  run again without --keep to remove them
#   --quick        host checks only (no pod)
#   --destructive  also run a real fork bomb inside the capped test pod
#
# Uses a throw-away project "agentbox-selftest" capped at 2 GiB RAM / 2 CPUs.
# Re-run after every update of: kernel, podman, passt, runsc, systemd.
set -uo pipefail
source "$(dirname "$(readlink -f "$0")")/../lib/common.sh"
B=$AB_ROOT/bin

RT=runsc KEEP=0 QUICK=0 DESTR=0
while (($#)); do
  case $1 in
    --runtime) RT=${2:?}; shift ;; --keep) KEEP=1 ;; --quick) QUICK=1 ;;
    --destructive) DESTR=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) ab_die "unknown option $1" ;;
  esac; shift
done

NP=0 NF=0 NW=0
pass() { ab_ok "$*"; NP=$((NP + 1)); }
fail() { ab_fail "$*"; NF=$((NF + 1)); }
warnc() { printf '%sWARN%s: %s\n' "$_Y" "$_N" "$*"; NW=$((NW + 1)); }
# expect <desc> <cmd...>        PASS if the command succeeds
# expect_not <desc> <cmd...>    PASS if the command fails
expect()     { local d=$1; shift; if "$@" >/dev/null 2>&1; then pass "$d"; else fail "$d"; fi; }
expect_not() { local d=$1; shift; if "$@" >/dev/null 2>&1; then fail "$d"; else pass "$d"; fi; }

P=agentbox-selftest POD=ab-agentbox-selftest
SLICE=agents-$(ab_norm "$P").slice
S=$AB_PROJECTS/$P W=$AB_AGENTS/$P
# Extra fixtures get fresh names per run; cleanup removes only what this run created.
RUNID=$(date +%s)-$$
P2=agentbox-selftest-b-$RUNID PL=agentbox-selftest-legacy-$RUNID
CAT2=agentbox-selftest-cat-$RUNID     # the second project is nested: $AB_PROJECTS/<cat>/<p2>
POD2=ab-$P2 S2=$AB_PROJECTS/$CAT2/$P2 W2=$AB_AGENTS/$P2 SLICE2=agents-$(ab_norm "$P2").slice
GI2=$AB_CONTEXT/groups/$CAT2 PI2=$AB_CONTEXT/project-instructions/$P2.md   # its folder + project instructions
GC2=$AB_CONFIG/groups/$CAT2                                                # its folder config (env)
MADE2=0 MADEL=0 MADEGD=0 MADEPD=0 MADECG=0
DATA=$HOME/agentbox-selftest-data SECRET=$HOME/.agentbox-selftest-secret
cx() { local c=$1; shift; podman exec "$POD-$c" bash -c "$*"; }   # run in a container

# ===========================================================================
ab_section "1. Host prerequisites"
for c in podman pasta nft git python3 tmux systemd-run curl runsc; do
  expect "command available: $c" command -v "$c"
done
pv=$(podman --version | awk '{print $3}')
[[ ${pv%%.*} -ge 5 ]] && pass "podman $pv" || fail "podman $pv is too old (need 5+)"
expect "python3 has tomllib (3.11+)" python3 -c 'import tomllib'
[[ $(podman info -f '{{.Host.Security.Rootless}}') == true ]] && pass "podman is rootless" || fail "podman is not rootless"
[[ $(podman info -f '{{.Host.CgroupsVersion}}') == v2 ]] && pass "cgroups v2" || fail "cgroups v1"
expect "subuid/subgid configured" grep -q "^$USER:" /etc/subuid
ctrl=$(cat "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers" 2>/dev/null)
for c in cpu memory pids; do
  [[ " $ctrl " == *" $c "* ]] && pass "cgroup controller delegated: $c" || fail "controller '$c' not delegated (run agentbox-prep.sh)"
done
bad=$(grep -rniE 'map-gw|map-host-loopback' /usr/share/containers /etc/containers "$HOME/.config/containers" 2>/dev/null | grep -v '^\s*#')
[[ -z $bad ]] && pass "no host-loopback mapping in containers.conf" || fail "host loopback mapped: $bad"
[[ -L $HOME/.config/containers/containers.conf.d/99-agentbox.conf ]] && pass "runsc registered (99-agentbox.conf)" || fail "99-agentbox.conf not linked"
hk=$(uname -r); gk=$(runsc --rootless --network=none "do" uname -r 2>/dev/null)
[[ -n $gk && $gk != "$hk" ]] && pass "runsc works standalone (guest kernel '$gk' != host '$hk')" || fail "runsc standalone failed"
systemctl is-active -q systemd-oomd && pass "systemd-oomd active" || warnc "systemd-oomd inactive (MemoryMax still protects)"
if command -v fish >/dev/null; then
  [[ $(readlink -f "$HOME/.config/fish/conf.d/agentbox.fish") == "$AB_ROOT/shell/agentbox.fish" ]] \
    && pass "fish integration linked" || warnc "fish integration not linked (run agentbox-prep.sh)"
fi
for sh in bash zsh; do
  command -v "$sh" >/dev/null && ! grep -qs "shell/agentbox.$sh" "$HOME/.${sh}rc" \
    && ab_info "$sh: ~/.${sh}rc does not source $AB_ROOT/shell/agentbox.$sh (fine if you do not use $sh)"
done
ab_info "linger: $(loginctl show-user "$USER" -p Linger --value 2>/dev/null)   (needed only for SSH-only machines)"
ab_info "filesystem of state dir: $(findmnt -no FSTYPE -T "$AB_STATE")"

ab_section "2. Images and agent CLIs"
for i in $(python3 "$AB_LIB/images.py" names); do
  if podman image exists "localhost/sbx-$i:latest"; then
    pass "image sbx-$i ($(podman image inspect -f '{{.Size}}' "localhost/sbx-$i:latest" | numfmt --to=iec))"
  else
    fail "image sbx-$i missing (run agentbox-build)"
  fi
done
ab_info "disk use (shared layers counted once):"; podman system df | sed 's/^/    /'
for t in bin/claude npm/bin/codex bin/agy bin/copilot npm/bin/npm; do
  [[ -x $AB_STATE/tools/$t ]] && pass "agent CLI present: ${t##*/}" || fail "agent CLI missing: ${t##*/} (agentbox-update-tools)"
done
[[ -f $AB_STATE/tools/VERSIONS ]] && sed 's/^/    /' "$AB_STATE/tools/VERSIONS"

((QUICK)) && { ab_section "Summary"; echo "PASS $NP  FAIL $NF  WARN $NW"; exit $((NF > 0)); }

# ===========================================================================
ab_section "3. Self-test project ($RT)"
cleanup() {
  [[ -n ${SRVPID1:-} ]] && kill "$SRVPID1" 2>/dev/null
  [[ -n ${SRVPID2:-} ]] && kill "$SRVPID2" 2>/dev/null
  if ((!KEEP)); then
    podman pod rm -f -t 2 "$POD" >/dev/null 2>&1
    podman unshare rm -rf "$W" "$AB_STATE/home/$P" 2>/dev/null
    rm -rf "$S" "$DATA" "$SECRET" "$AB_STATE/bridge/$P.git" "$AB_STATE/ctx/$P" "$AB_CONTEXT/projects/$P"
    rm -f "$HOME/.config/systemd/user/$SLICE"
  fi
  if ((MADE2)); then
    podman pod rm -f -t 2 "$POD2" >/dev/null 2>&1
    podman unshare rm -rf "$W2" "$AB_STATE/home/$P2" 2>/dev/null
    rm -rf "${AB_PROJECTS:?}/$CAT2" "$AB_STATE/bridge/$P2.git" "$AB_STATE/ctx/$P2" "$AB_CONTEXT/projects/$P2" \
      "$GI2" "$PI2"
    ((MADEGD)) && rmdir "$AB_CONTEXT/groups" 2>/dev/null
    ((MADEPD)) && rmdir "$AB_CONTEXT/project-instructions" 2>/dev/null
    rm -f "$GC2/group.toml"; rmdir "$GC2" 2>/dev/null
    ((MADECG)) && rmdir "$AB_CONFIG/groups" 2>/dev/null
    rm -f "$HOME/.config/systemd/user/$SLICE2"
  fi
  ((MADEL)) && podman pod rm -f -t 2 "ab-$PL" >/dev/null 2>&1
}
trap cleanup EXIT
podman pod rm -f -t 2 "$POD" >/dev/null 2>&1
podman unshare rm -rf "$W" 2>/dev/null; rm -rf "$S" "$AB_STATE/bridge/$P.git"
mkdir -p "$S" "$DATA"; echo "readonly-data" > "$DATA/data.txt"; echo "HOST-SECRET" > "$SECRET"
rm -rf "$AB_CONTEXT/projects/$P"; mkdir -p "$AB_CONTEXT/projects/$P"
echo "private selftest notes" > "$AB_CONTEXT/projects/$P/AGENTS.md"
git -C "$S" init -q -b main && echo "# selftest" > "$S/README.md" \
  && git -C "$S" add . && git -C "$S" -c user.name=t -c user.email=t@t commit -qm init
expect "new worktree + read-only bridge" "$B/agentbox-new-worktree" "$P"
UPOPTS=(--runtime "$RT" --mem 2G --cpus 2 --ro "$DATA")
if "$B/agentbox-up" "$P" "${UPOPTS[@]}"; then pass "pod started"; else fail "pod failed to start"; exit 1; fi
for c in claude codex agy copilot dev; do
  [[ $(podman inspect -f '{{.State.Running}}' "$POD-$c" 2>/dev/null) == true ]] \
    && pass "container $c running" || fail "container $c not running"
done

# ===========================================================================
ab_section "4. Filesystem isolation"
expect_not "host home not visible" cx dev "test -e '/home/$USER'"
expect_not "host secret file not findable" cx dev "find /home /work /tmp /opt /etc /data /ref /upstream /root -name .agentbox-selftest-secret 2>/dev/null | grep -q ."
expect     "write to /work works" cx dev "touch /work/.ab-write-test"
[[ $(stat -c %U "$W/.ab-write-test" 2>/dev/null) == "$USER" ]] && pass "files in /work are owned by $USER on host" \
  || fail "ownership of new files is $(stat -c %U "$W/.ab-write-test" 2>/dev/null)"
expect_not "root filesystem is read-only" cx dev "touch /usr/.x"
expect_not "agent CLIs are read-only" cx dev "touch /opt/agentbox/tools/.x"
expect_not "/upstream (bridge) is read-only" cx dev "touch /upstream/.x"
expect     "/ref/<data> readable" cx dev "grep -q readonly-data /ref/agentbox-selftest-data/data.txt"
expect_not "/ref/<data> not writable" cx dev "echo x >> /ref/agentbox-selftest-data/data.txt"
expect_not "/ref/<data> cannot be remounted rw" cx dev "mount -o remount,rw /ref/agentbox-selftest-data"
expect     "no capabilities (CapEff=0)" cx dev "grep -q 'CapEff:\s*0000000000000000' /proc/self/status"
expect_not "no SSH agent / D-Bus / tokens in env" cx dev "env | grep -Eiq '^(SSH_AUTH_SOCK|DBUS_SESSION|GH_TOKEN|GITHUB_TOKEN|AWS_|ANTHROPIC_API|OPENAI_API)'"
expect     "sandbox context file present" cx claude "grep -q 'Sandbox context' /etc/agentbox/context.md"
expect     "AGENTBOX env vars set" cx claude 'test "$AGENTBOX" = 1 -a -n "$AGENTBOX_HOST"'
expect     "Claude sees its CLAUDE.md" cx claude "grep -q 'Sandbox context' ~/.claude/CLAUDE.md"
expect     "Codex sees its AGENTS.md" cx codex "grep -q 'Sandbox context' ~/.codex/AGENTS.md"
expect     "Antigravity sees its GEMINI.md" cx agy "grep -q 'Sandbox context' ~/.gemini/GEMINI.md"
expect     "Copilot sees its copilot-instructions.md" cx copilot "grep -q 'Sandbox context' ~/.copilot/copilot-instructions.md"
expect_not "Copilot token is NOT visible to other agents" cx claude "env | grep -q COPILOT_GITHUB_TOKEN"
expect     "updated npm is first in PATH" cx dev 'test "$(command -v npm)" = /opt/agentbox/tools/npm/bin/npm'

ab_section "5. Credential separation"
declare -A own=([claude]=.claude [codex]=.codex [agy]=.gemini [copilot]=.copilot)
for c in claude codex agy copilot dev; do
  for o in claude codex agy copilot; do
    [[ $c == "$o" ]] && continue
    expect_not "$c cannot see $o login (~/${own[$o]})" cx "$c" "test -e ~/${own[$o]}"
  done
done

# Config folders (logins, conversations) are per project: a second project must not
# see the first one's files. Each assertion is one successful exec in a running
# container, so a failed exec never counts as isolation.
# Every path cleanup can remove must be new (symlinks included) before the run claims it.
fixture_free() {  # fixture_free <path>...  -> fails if any exists
  local f; for f in "$@"; do [[ -e $f || -L $f ]] && return 1; done; return 0
}
fixture_free "$AB_CONTEXT/groups" && MADEGD=1                 # parents: remove later only if new
fixture_free "$AB_CONTEXT/project-instructions" && MADEPD=1
fixture_free "$AB_CONFIG/groups" && MADECG=1
if ! fixture_free "$AB_PROJECTS/$CAT2" "$W2" "$AB_STATE/home/$P2" "$AB_STATE/bridge/$P2.git" "$AB_STATE/ctx/$P2" \
     "$AB_CONTEXT/projects/$P2" "$HOME/.config/systemd/user/$SLICE2" "$GI2" "$PI2" "$GC2" || podman pod exists "$POD2"; then
  fail "fixture $P2 already exists; not touching it"
elif MADE2=1 && mkdir -p "$GI2" "$AB_CONTEXT/project-instructions" && echo "selftest-folder-instr" > "$GI2/group.md" \
  && echo "selftest-project-instr" > "$PI2" \
  && mkdir -p "$GC2" && printf '[project]\nenv = { AB_SELFTEST = "env-%s" }\n' "$RUNID" > "$GC2/group.toml" \
  && cx dev "echo agents-$RUNID > /work/ab-ref-agents" && echo "project-$RUNID" > "$S/ab-ref-project" \
  && mkdir -p "$S2" && git -C "$S2" init -q -b main && echo "# selftest2" > "$S2/README.md" \
  && git -C "$S2" add . && git -C "$S2" -c user.name=t -c user.email=t@t commit -qm init \
  && "$B/agentbox-new-worktree" "$P2" >/dev/null \
  && "$B/agentbox-up" "$P2" "${UPOPTS[@]}" --ro "agents:$P" --ro "project:$P" >/dev/null; then
  pass "second project (nested in a category folder) started"
  "$B/agentbox" list "$CAT2" 2>/dev/null | grep -q "^  $P2 " \
    && pass "agentbox list shows it under its category" || fail "agentbox list does not show $CAT2/$P2"
  declare -A ins=([claude]=.claude/CLAUDE.md [codex]=.codex/AGENTS.md [agy]=.gemini/GEMINI.md
                  [copilot]=.copilot/copilot-instructions.md)
  for c in claude codex agy copilot; do
    d=${own[$c]} ma=.ab-a-$RANDOM mb=.ab-b-$RANDOM
    expect "$c: project 1 writes a marker in ~/$d" podman exec "$POD-$c" bash -c "echo a > ~/$d/$ma"
    expect "$c: project 2 writes its own marker and cannot see project 1's" podman exec "$POD2-$c" \
      bash -c "echo b > ~/$d/$mb && test -f ~/$d/$mb && ! test -e ~/$d/$ma"
    expect "$c: project 1 cannot see project 2's marker" podman exec "$POD-$c" \
      bash -c "test -f ~/$d/$ma && ! test -e ~/$d/$mb"
    expect "$c: instruction file in place in project 2" podman exec "$POD2-$c" \
      bash -c "grep -q 'Sandbox context' ~/${ins[$c]}"
  done
  expect "folder, then project instructions in project 2's context" podman exec "$POD2-claude" \
    bash -c "awk '/selftest-folder-instr/{g=NR} /selftest-project-instr/{p=NR} END{exit !(g && p && g < p)}' ~/${ins[claude]}"
  # [project] env from the folder config; references to project 1 (agents: then project:).
  for c in claude dev; do
    expect "$c: [project] env arrives" podman exec "$POD2-$c" bash -c "test \"\$AB_SELFTEST\" = env-$RUNID"
  done
  expect "project 1 reads its private AGENTS.md (control)" cx claude "grep -q 'private selftest notes' /work/AGENTS.md"
  expect "agents:$P shows project 1's agent copy, read-only, without its private files" podman exec "$POD2-claude" \
    bash -c "grep -qx agents-$RUNID /ref/$P/ab-ref-agents && ! test -e /ref/$P/ab-ref-project \
      && test -L /ref/$P/AGENTS.md && ! cat /ref/$P/AGENTS.md 2>/dev/null \
      && d=\$(ls -A /ref/$P/.agentbox) && test -z \"\$d\" && ! touch /ref/$P/.ab-x 2>/dev/null"
  expect "project:$P shows project 1's repository, read-only" podman exec "$POD2-claude" \
    bash -c "grep -qx project-$RUNID /ref/${P}_2/ab-ref-project && ! test -e /ref/${P}_2/ab-ref-agents \
      && ! touch /ref/${P}_2/.ab-x 2>/dev/null"
else
  fail "second project failed to start"
fi

# A pod from an older agentbox (no layout label) must be refused while it runs, also
# when only some of its containers run (Degraded). No network, nothing but sleep.
legacy_refused() {  # legacy_refused <state description>
  local cmd out args
  for cmd in agentbox-enter agentbox-up; do
    args=("$PL"); [[ $cmd == agentbox-enter ]] && args+=(dev true)
    if out=$("$B/$cmd" "${args[@]}" 2>&1); then
      fail "$cmd entered a $1 pod without the layout label"
    elif [[ $out == *"agentbox $PL restart"* ]]; then
      pass "$cmd refuses a $1 pod from an older agentbox"
    else
      fail "$cmd failed on the $1 legacy pod without the restart message: ${out##*$'\n'}"
    fi
  done
}
if podman pod exists "ab-$PL"; then
  fail "fixture ab-$PL already exists; not touching it"
else
  MADEL=1
  img=localhost/sbx-base:latest
  lstate() { podman pod inspect -f '{{.State}}' "ab-$PL" 2>/dev/null; }
  if podman pod create --name "ab-$PL" --network none >/dev/null \
     && ab_scoped "$SLICE" "ab-legacy-infra" podman pod start "ab-$PL" >/dev/null \
     && ab_scoped "$SLICE" "ab-legacy-dev" podman run -d --pod "ab-$PL" --name "ab-$PL-dev" \
          --cap-drop=all --read-only "$img" sleep 300 >/dev/null \
     && [[ $(lstate) == Running ]]; then
    legacy_refused running
    # A second container that exits leaves the pod Degraded (only some containers run).
    if ab_scoped "$SLICE" "ab-legacy-done" podman run --pod "ab-$PL" --name "ab-$PL-done" \
         --cap-drop=all --read-only "$img" true >/dev/null && [[ $(lstate) == Degraded ]]; then
      legacy_refused degraded
    else
      fail "legacy pod fixture did not reach Degraded (state '$(lstate)'): degraded case not tested"
    fi
  else
    fail "legacy pod fixture did not reach Running (state '$(lstate)'): legacy guard not tested"
  fi
  podman pod rm -f -t 2 "ab-$PL" >/dev/null 2>&1
fi

# ===========================================================================
ab_section "6. Network isolation"
NS=$(podman inspect -f '{{.NetworkSettings.SandboxKey}}' "$(podman pod inspect -f '{{.InfraContainerID}}' "$POD")")
expect "egress rules loaded in pod netns" podman unshare nsenter --net="$NS" nft list table inet agentbox
# Public internet: test sites the agents need. The host is the control: if a
# site fails from the host too, the cause is outside the sandbox (WARN, not FAIL).
for url in https://pypi.org/simple/ https://registry.npmjs.org/ https://api.anthropic.com/; do
  if ! curl -sS -m 10 -o /dev/null "$url" 2>/dev/null; then
    warnc "$url unreachable from the HOST too (network/ISP issue, not the sandbox)"
  elif cx dev "curl -sS -m 10 -o /dev/null '$url'"; then
    pass "public internet from sandbox: $url"
  else
    fail "$url works from host but NOT from sandbox"
  fi
done
expect "DNS lookups work (getent hosts pypi.org)" cx dev "timeout 10 getent hosts pypi.org"
if grep -q '169.254.1.1' <<<"$(cx dev 'cat /etc/resolv.conf')"; then
  expect_not "only DNS reaches the forwarder (169.254.1.1:80 blocked)" cx dev "curl -fs -m 3 http://169.254.1.1/"
fi
expect "public git fetch allowed" cx dev "git ls-remote https://github.com/git/git HEAD"
expect "port 443 to github.com open (control)" cx dev "nc -z -w 5 github.com 443"
expect_not "SSH (port 22) to github.com blocked" cx dev "nc -z -w 5 github.com 22"
PORT=$((20000 + RANDOM % 20000))
python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 & SRVPID1=$!
python3 -m http.server $((PORT + 1)) --bind 0.0.0.0 >/dev/null 2>&1 & SRVPID2=$!
sleep 1
expect_not "host loopback service unreachable (host.containers.internal)" cx dev "curl -fs -m 3 http://host.containers.internal:$PORT"
expect_not "host loopback service unreachable (169.254.1.2)" cx dev "curl -fs -m 3 http://169.254.1.2:$PORT"
lan=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src") print $(i+1)}')
if [[ -n $lan ]]; then
  expect     "(control) host LAN service reachable from host itself" curl -fs -m 3 "http://$lan:$((PORT + 1))"
  expect_not "host LAN address $lan blocked from sandbox" cx dev "curl -fs -m 3 http://$lan:$((PORT + 1))"
fi
gw=$(ip -4 route show default | awk '{print $3; exit}')
[[ -n $gw ]] && expect_not "LAN gateway $gw:80 blocked" cx dev "curl -fs -m 3 http://$gw"
if command -v tailscale >/dev/null && ts=$(tailscale ip -4 2>/dev/null) && [[ -n $ts ]]; then
  expect_not "tailnet address $ts blocked" cx dev "curl -fs -m 3 http://$ts:$((PORT + 1))"
  expect_not "Tailscale MagicDNS 100.100.100.100 blocked" cx dev "nc -z -w 3 100.100.100.100 53"
else
  ab_info "tailscale not running here: tailnet tests skipped (range 100.64.0.0/10 is blocked anyway)"
fi
blk=$("$B/agentbox" "$P" blocked 2>/dev/null)
echo "$blk" | sed 's/^/    /'
echo "$blk" | awk '$1=="ssh" && $2>0 {s=1} $1=="lan" && $2>0 {l=1} END {exit !(s && l)}' \
  && pass "blocked attempts are counted (agentbox <p> blocked)" || fail "blocked counters did not increase"
cx dev "nohup python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 &" ; sleep 2
expect "pod-local localhost works between containers (dev -> claude)" cx claude "curl -fs -m 3 http://127.0.0.1:8765"

# ===========================================================================
ab_section "7. Kernel isolation"
gk=$(cx dev "uname -r")
if [[ $RT == runsc ]]; then
  [[ $gk != "$hk" ]] && pass "agents see gVisor kernel '$gk', not host '$hk'" || fail "agents see the host kernel"
else
  ab_info "runtime crun: agents share the host kernel ($gk) — expected for crun"
fi

# ===========================================================================
ab_section "8. Resource caps"
[[ $(systemctl --user show agents.slice -p MemoryMax --value) != infinity ]] \
  && pass "agents.slice MemoryMax = $(systemctl --user show agents.slice -p MemoryMax --value | numfmt --to=iec)" \
  || fail "agents.slice has no MemoryMax"
pm=$(systemctl --user show "$SLICE" -p MemoryMax --value)
[[ $pm == 2147483648 ]] && pass "project slice MemoryMax = 2G (test cap)" || fail "project slice MemoryMax = $pm"
outside=() n=0
podid=$(podman pod inspect -f '{{.Id}}' "$POD")
infra=$(podman pod inspect -f '{{.InfraContainerID}}' "$POD")   # catatonit only: not checked
keys=($(podman ps -q --no-trunc --filter "pod=$POD" | grep -v "$infra") "$(basename "$NS")")
for pid in $(pgrep -u "$USER" -f 'runsc|conmon|pasta'); do
  cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null) || continue
  hit=0; for k in "${keys[@]}"; do [[ -n $k && $cmd == *"$k"* ]] && hit=1 && break; done
  ((hit)) || continue; n=$((n + 1))
  cg=$(cut -d: -f3 "/proc/$pid/cgroup" 2>/dev/null)
  # runsc/pasta: capped by agents.slice. crun conmon: capped by the pod cgroup limits.
  [[ $cg == *"/agents.slice/"* || $cg == *"libpod_pod_$podid"* ]] || outside+=("$pid ${cmd:0:40} -> $cg")
done
ab_info "found $n runsc/conmon/pasta processes belonging to the pod"
((n > 0)) || fail "could not find the pod's processes (check by hand: systemd-cgls --user-unit agents.slice)"
if ((${#outside[@]} == 0)); then pass "all runsc/conmon/pasta processes of the pod are capped (slice or pod cgroup)"
else fail "processes outside agents.slice (caps NOT enforced for them):"; printf '    %s\n' "${outside[@]}"; fi
pcg=$(podman pod inspect -f '{{.CgroupPath}}' "$POD" 2>/dev/null)
pmax=$(cat "/sys/fs/cgroup/$pcg/memory.max" 2>/dev/null)
[[ $pmax == 2147483648 ]] && pass "pod cgroup memory.max = 2G (caps crun containers)" \
  || fail "pod cgroup memory.max = '${pmax:-?}' (path: $pcg)"
expect "thread variables set (OMP_NUM_THREADS=2)" cx dev 'test "$OMP_NUM_THREADS" = 2'

ab_step "CPU cap: 8 busy loops for 6 s, cap is 2 CPUs"
u0=$(systemctl --user show "$SLICE" -p CPUUsageNSec --value)
cx dev 'for i in 1 2 3 4 5 6 7 8; do timeout 6 sh -c "while :; do :; done" & done; wait' >/dev/null 2>&1
u1=$(systemctl --user show "$SLICE" -p CPUUsageNSec --value)
if [[ $u0 =~ ^[0-9]+$ && $u1 =~ ^[0-9]+$ ]]; then
  cores=$(awk -v a="$u0" -v b="$u1" 'BEGIN{printf "%.2f", (b-a)/6e9}')
  awk -v c="$cores" 'BEGIN{exit !(c <= 2.4)}' && pass "CPU limited to ~$cores cores" || fail "CPU used $cores cores (> 2)"
else
  warnc "CPU accounting not available for the slice"
fi

ab_step "memory cap: allocate 3 GiB in dev (cap 2 GiB)"
out=$(cx dev "timeout 90 python3 -c \"b=b'x'*(3*2**30); print('ALLOC_OK')\"" 2>&1)
if [[ $out == *ALLOC_OK* ]]; then fail "3 GiB allocation succeeded (memory cap not enforced)"
else pass "3 GiB allocation was stopped (host unaffected)"; fi
st=$(podman inspect -f '{{.State.Running}}' "$POD-dev" 2>/dev/null)
ab_info "dev container running after OOM: $st (under gVisor the whole container may be killed — expected)"
expect "other agent containers survived the OOM" cx claude true
"$B/agentbox-up" "$P" "${UPOPTS[@]}" >/dev/null 2>&1   # recreate dev if it died

if ((DESTR)); then
  ab_step "fork bomb in dev (destructive mode)"
  t0=$(date +%s)
  cx dev "timeout 20 bash -c ':(){ :|:& };:'" >/dev/null 2>&1
  t1=$(date +%s); expect "host still responsive after fork bomb" timeout 5 systemctl --user is-system-running
  ab_info "fork bomb ran $((t1 - t0)) s"; podman pod rm -f "$POD" >/dev/null 2>&1
  "$B/agentbox-up" "$P" "${UPOPTS[@]}" >/dev/null 2>&1
else
  expect "300 processes can start (normal parallel work)" cx dev 'for i in $(seq 300); do sleep 3 & done; wait'
  ab_info "real fork bomb skipped (use --destructive). Under gVisor, guest processes are bounded by the RAM cap."
fi

# ===========================================================================
ab_section "9. Git guardrails"
expect     "agent can commit" cx claude "cd /work && git commit -q --allow-empty -m 'agent test commit'"
hn=$(git config --global --get user.name 2>/dev/null || true)
an=$(cx claude "cd /work && git log -1 --format='%an|%cn'")
if [[ -n $hn ]]; then
  [[ $an == "$hn|$hn" ]] && pass "commit author/committer = your host identity ($hn), as configured by default" \
    || ab_info "commit author|committer = '$an' (check your [git] settings if you changed them)"
else
  ab_info "no host git identity; commit author|committer = '$an'"
fi
expect     "agent git config is read-only (cannot change identity globally)" \
  bash -c "! podman exec $POD-claude git config --global user.name x 2>/dev/null"
expect     "commit --author still overrides the identity" cx claude \
  "cd /work && git commit -q --allow-empty --author='Solo Agent <solo@agentbox.invalid>' -m t2 && git log -1 --format=%an | grep -q 'Solo Agent'"
expect_not "agent cannot push to /upstream" cx claude "cd /work && git push -q upstream HEAD:refs/heads/x"
expect_not "agent cannot push over https" cx claude "cd /work && git push -q https://github.com/git/git HEAD:refs/heads/x"
expect     "agent can fetch your commits (git fetch upstream)" cx claude "cd /work && git fetch -q upstream"
cx claude "cd /work && git config core.fsmonitor 'touch FSMON_PWNED; false'"
expect "host fetch of agent commits (agentbox fetch)" "$B/agentbox" "$P" fetch
[[ -e $W/FSMON_PWNED ]] && fail "planted fsmonitor ran during host fetch" || pass "planted fsmonitor did NOT run during host fetch"
expect "agent commit arrived in your repo as agent/main" git -C "$S" rev-parse -q --verify refs/remotes/agent/main
for sh in bash zsh fish; do
  command -v "$sh" >/dev/null || continue
  case $sh in
    bash) run_sh=(bash -c);  src="source '$AB_ROOT/shell/agentbox.bash'" ;;
    zsh)  run_sh=(zsh -fc);  src="source '$AB_ROOT/shell/agentbox.zsh'" ;;
    fish) run_sh=(fish -c);  src="source '$AB_ROOT/shell/agentbox.fish'" ;;
  esac
  g=$("${run_sh[@]}" "$src; cd '$W'; echo \$GIT_DIR" 2>/dev/null)
  [[ $g == /nonexistent/agentbox-guard ]] && pass "$sh guard disables git inside $W" || fail "$sh guard not active in $W"
  "${run_sh[@]}" "$src; cd '$W'; git status" >/dev/null 2>&1
  [[ -e $W/FSMON_PWNED ]] && fail "git in a guarded $sh shell ran the planted command" || pass "git in guarded $sh shell is harmless"
done
env -u GIT_DIR git -C "$W" status >/dev/null 2>&1
[[ -e $W/FSMON_PWNED ]] && ab_info "control: UNGUARDED host git in the agent copy DID run the planted command — this is why the guard exists" \
  || ab_info "control: unguarded git did not trigger fsmonitor on this git version"
cx claude "cd /work && git config --unset core.fsmonitor; rm -f FSMON_PWNED"

# ===========================================================================
ab_section "10. Agent context (private files, skills)"
expect     "private AGENTS.md linked into /work" cx claude "grep -q 'private selftest notes' /work/AGENTS.md"
expect     "agents can write private files (/work/.agentbox)" cx claude "echo from-agent > /work/.agentbox/agent-note.md"
[[ -f $AB_CONTEXT/projects/$P/agent-note.md ]] && pass "private file arrived in $AB_CONTEXT/projects/$P" \
  || fail "private file did not reach $AB_CONTEXT/projects/$P"
expect     "links are excluded from git (not committable by accident)" cx claude \
  "cd /work && test -z \"\$(git status --porcelain -- AGENTS.md .agentbox)\""
sm=$(AB_CFG_QUIET=1 python3 "$AB_LIB/cfg.py" "$P" 2>/dev/null | sed -n "s/^SKILLS_MODE=//p" | tr -d "'")
if [[ $sm == ro && -d $AB_CONTEXT/skills ]]; then
  expect_not "shared skills are read-only" cx claude "touch /home/agent/.claude/skills/.x"
else
  ab_info "skills mode: ${sm:-?} (read-only test skipped)"
fi

ab_section "11. Agent tool kit"
for t in pdftotext pdfinfo qpdf gs convert magick exiftool pandoc sqlite3 7z rg fd jq shellcheck; do
  expect "tool in image: $t" cx dev "command -v $t"
done
expect "PDF -> PNG works (ImageMagick + Ghostscript)" cx dev \
  "cd /tmp && gs -q -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -o t.pdf -c 'showpage' && magick t.pdf t.png && test -s t.png"
expect "PDF text extraction works (pdftotext)" cx dev "cd /tmp && pdftotext t.pdf - >/dev/null"

ab_section "12. Shared caches"
expect "uv install into a venv (shared cache)" cx dev "cd /tmp && uv venv -q v && uv pip install -q --python v six"
[[ -n $(ls -A "$AB_STATE/cache/uv" 2>/dev/null) ]] && pass "uv cache populated on host" || fail "uv cache empty"
if command -v compsize >/dev/null; then ab_info "run 'sudo compsize <venv> $AB_STATE/cache/uv' on a real project to see reflink sharing"; fi

ab_section "13. Manual checks (not automated)"
cat <<EOF
  - Logins: agentbox <project> claude / codex / agy -> log in once per project (copilot: token file, see README);
    restart -> still logged in; a second project asks for its own login.
  - Persistence: start an agent inside host tmux, detach (Ctrl-b d), close the terminal, reattach.
  - Never open $AB_AGENTS/* in an IDE with git integration.
EOF

ab_section "Summary ($RT)"
echo "PASS $NP   FAIL $NF   WARN $NW"
((KEEP)) && ab_info "kept: pod $POD, $S, $W (remove: agentbox-down $P; rerun without --keep)"
exit $((NF > 0))
