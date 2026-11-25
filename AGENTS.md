# Working on agentbox

Instructions for anyone changing this repository, human or agent. Read this file
completely before you change code. The roadmap is in `docs/ROADMAP.md`.

agentbox builds the sandbox that agents run in, and its scripts run **on the host, as
the user**. A mistake here can weaken the sandbox for every project. Be conservative.

## Goals

- Small and readable: bash scripts plus small stdlib-only Python helpers. No daemon, no
  new host dependencies without a strong reason.
- Linux, rootless Podman, gVisor by default, `crun` as a per-project fallback.
- The check suite (`scripts/agentbox-check.sh`) is the definition of "works".

## Security invariants (never break these)

1. **Never mount** into a container: the Podman/Docker socket, `$HOME`, `/run/user/$UID`,
   D-Bus or Wayland/X11 sockets, SSH/GPG agent sockets, `~/.config/agentbox` (the sandbox
   rules), the agentbox package itself, or another agent's login folder.
2. **No credentials** that allow `git push` inside a sandbox. TCP 22 stays blocked.
3. **Folders agents can write** (`~/.agents-projects/*`, agent homes, login folders,
   `~/.agents-context/projects/*`) are untrusted on the host:
   - create folders there only with `ab_safe_mkdir` (no `mkdir -p`, no `touch` through paths
     that may be symlinks);
   - do file operations inside those folders **inside a container** (`podman exec`), not on
     the host;
   - never run host `git` in an agent copy, except `fetch` from the trusted repository with
     `-c core.fsmonitor=false -c core.hooksPath=/dev/null`.
4. The host **never executes, sources, `eval`s or pastes** content written by agents. If a
   host script must read an agent-written file (for example a status file), parse a fixed
   set of allowed values, cap the size, and ignore everything else.
5. Published ports bind to `127.0.0.1` only.
5a. Data that differs per project (agent sessions, history, private files) never lives in a
   folder shared by all projects; only logins and read-only tools/skills are shared.
6. Project repositories are untrusted input for the launcher: `.agentbox-hint.toml` may
   only lower privileges. Mounts, ports and runtime come only from `~/.config/agentbox`.
7. Resource caps come from the systemd slice; every `podman` call that starts processes
   runs through `ab_scoped` so conmon/pasta/runsc stay in the slice.

## Hard-won facts (do not "simplify" these away)

- Rootless runsc needs `--runtime-flag=ignore-cgroups` **and** `--runtime-flag=network=host`.
  With `ignore-cgroups`, Podman's `--memory/--cpus` do nothing for runsc; the slice caps it.
- Pods: `--share net` only. gVisor cannot join another container's UTS/IPC namespaces.
- Pods: no `--userns=keep-id` (gVisor's gofer cannot join the infra's user namespace).
  Agents run as container root = the host user, without capabilities. Claude Code needs
  `IS_SANDBOX=1` for bypass mode as root.
- Pods: no `--cgroup-parent` (Podman 6 fails to start the pod: "unit already loaded").
- No `--hostname` per container when UTS is shared; we set it per container because UTS
  is not shared.
- nftables rules are loaded into the pod's network namespace from the host
  (`podman unshare nsenter --net=...`); agents have no `CAP_NET_ADMIN`.
- Bind-mounted files that the host rewrites (git config, context files) must keep their
  inode: write to a temp file, then `cat tmp > target`.
- Plain `tar x` over the repository never deletes files; say so in update instructions.

## Before you commit

- `shellcheck -x -S warning -e SC1091,SC2207 bin/* scripts/*.sh lib/common.sh images/*/setup.sh shell/agentbox.bash`
- `python3 -m py_compile lib/*.py`, and the tests in `tests/` if the change touches them.
- `scripts/agentbox-check.sh` and `scripts/agentbox-check.sh --runtime crun` on a real
  host when the change affects containers, mounts, network, caps or git handling. Add a
  check for every new security-relevant behaviour.
- Update `README.md` (user-facing), `CHANGELOG.md` (under the next version) and
  `examples/` when behaviour or configuration changes.
- One roadmap item per commit. Commit messages: imperative summary line, then what and
  why. Follow the trailer convention the maintainer gives you in your instructions.

## Style

- Bash: `set -euo pipefail`, quote everything, arrays for argument lists, helpers from
  `lib/common.sh` (`ab_die`, `ab_warn`, `ab_ok`, ...).
- Python: standard library only (3.11+, `tomllib`), no third-party packages.
- Messages to users: short, plain sentences; say what to do next.
- Minimal code that works. Don't add options nobody asked for.
