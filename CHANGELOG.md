# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org);
before 1.0, minor versions may change the configuration format.

## Unreleased

- Image layers can `include` other layers: their own parts are applied before the
  layer's own, e.g. `[webdocs] parent = "web"`, `include = ["docs"]` (see
  `examples/images/profiles.toml`). Layers that use `docs` get TeX Live mounted; the
  mounted folder now goes through the usual mount checks, so a TeX Live directly in your
  home folder is refused instead of exposing all of `$HOME`. Setup scripts keep their
  order with ten or more parts.
- Projects can live in subfolders of `~/Projects`, up to four levels deep (for example
  `research/Survey/Survey-paper`). The name is still the repository's folder name; two
  repositories with the same name are refused until one is renamed. `agentbox list`
  shows a tree and filters by folder (`agentbox list research`) or by `tags = [...]` in
  the project file (`agentbox list --tag paper`). Shell completion finds nested projects.
  Changed: symlinked folders in `~/Projects` are no longer projects (each project has one
  path), and a project needs its own `.git` folder, so linked worktrees are not projects
  (they share the main checkout's remotes). Move such repositories into `~/Projects`, or
  use the main checkout.
- Privacy fix: each agent's config folder (login, settings, conversations, history) is now
  per project, in `~/.local/share/agentbox/home/<project>/<agent>/`. Before, one folder in
  `~/.local/share/agentbox/auth/` was shared by all projects: `/resume` mixed projects,
  `--continue` could pick up another project's conversation, and an agent could read
  other projects' transcripts. Claude Code, Codex and Antigravity now ask you to log in
  once per project; the Copilot token file stays shared.
  Upgrade: restart running pods (`agentbox <project> restart`; agentbox refuses to enter
  pods started by the old version) and log in again. The old folders
  `~/.local/share/agentbox/auth/{claude,codex,agy,copilot}/` are no longer used; they hold
  the old conversations of all projects. Delete them yourself when you no longer need
  them (keep `auth/copilot.env`); agentbox never deletes them.
- Base image: `bubblewrap` and `socat` added, because agent CLIs check for them at
  startup. They stay unused: agentbox itself is the sandbox. Rebuild with `agentbox-build`.

## 0.1.1 — 2026-11-25

- Fix: DNS now goes through Podman's pasta forwarder (169.254.1.1) to the host's own
  resolver, so lookups work on networks that block outside DNS servers. The egress rules
  allow port 53 to that address only. Set `[network] dns = ["9.9.9.9", "1.1.1.1"]` to use
  public resolvers as before.

## 0.1.0 — 2026-11-25

First public version, licensed under GPL-3.0-or-later.

- Rootless Podman pods with gVisor (`runsc`) by default, `crun` per project or per run.
- One container per agent (Claude Code, Codex CLI, Antigravity CLI, GitHub Copilot CLI)
  plus a `dev` container without logins.
- Egress rules in each pod: LAN, tailnet, link-local, host loopback and SSH blocked;
  `agentbox <project> blocked` shows refused attempts.
- Git bridge: agents work on a copy, you fetch their commits; no credentials in the sandbox.
- Resource caps through systemd user slices; thread variables follow the caps.
- Image layers as folders (`packages.txt`, `files/`, `setup.sh`, `env.txt`), extendable from
  your own config.
- Agent context folder: global instructions, shared skills, private per-project files.
- Shell integration for bash, zsh and fish (PATH, completion, git guard).
- Check suite: `scripts/agentbox-check.sh`.
