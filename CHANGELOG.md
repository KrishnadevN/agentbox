# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org);
before 1.0, minor versions may change the configuration format.

## Unreleased

## 0.2.0-beta.1 — 2026-11-26

Upgrading from 0.1:

1. Stop all pods **before** updating: `agentbox down-all`. (If you already updated, stop
   each old pod with `agentbox-down <project>`: the new `agentbox <project> down` looks
   the project up first, and agentbox refuses to enter pods started by 0.1.)
2. Update: `git -C ~/.agentbox fetch --tags && git -C ~/.agentbox checkout v0.2.0-beta.1`.
3. Rebuild the images with `agentbox-build` (new packages, and the mount point for
   shared agent defaults).
4. Before starting any project, check `~/Projects`: symlinked folders and linked
   worktrees are no longer projects, and folder names that cannot be a pod name or are
   reserved for agentbox commands (such as `rename`) get an error that says so. Move a
   symlinked repository into `~/Projects`, and rename a folder whose name can't be used.
   Whenever the name changes (the old name was the symlink's or the folder's), run
   `agentbox rename <old> <new>` **before** the first start under the new name, to keep
   the agent copy, logins and private files: a start creates a fresh copy under the new
   name, and rename then refuses to overwrite it.
5. Start your projects as usual and log in again in each, because agent config folders
   are now per project, or set up the shared Claude token (README, "Logging in").
6. The old folders `~/.local/share/agentbox/auth/{claude,codex,agy,copilot}/` are no
   longer used; they hold the old conversations of all projects. Delete them when you no
   longer need them (keep `auth/copilot.env`); agentbox never deletes them.

Changes:

- Privacy fix: each agent's config folder (login, settings, conversations, history) is now
  per project, in `~/.local/share/agentbox/home/<project>/<agent>/`. Before, one folder in
  `~/.local/share/agentbox/auth/` was shared by all projects: `/resume` mixed projects,
  `--continue` could pick up another project's conversation, and an agent could read
  other projects' transcripts. Claude Code, Codex and Antigravity now ask you to log in
  once per project; the Copilot token file stays shared.
- Projects can live in subfolders of `~/Projects`, up to four levels deep (for example
  `research/Survey/Survey-paper`). The name is still the repository's folder name; two
  repositories with the same name are refused until one is renamed. `agentbox list`
  shows a tree and filters by folder (`agentbox list research`) or by `tags = [...]` in
  the project file (`agentbox list --tag paper`). Shell completion finds nested projects.
  Changed: symlinked folders in `~/Projects` are no longer projects (each project has one
  path), and a project needs its own `.git` folder, so linked worktrees are not projects
  (they share the main checkout's remotes). Move such repositories into `~/Projects`, or
  use the main checkout.
- Settings and instructions per folder of `~/Projects`:
  `~/.config/agentbox/groups/<folder>/group.toml` applies to every project below that
  folder (nested folders mirror `~/Projects`, outer first), and
  `~/.agents-context/groups/<folder>/group.md` is added to their agents' context.
  Instruction modules: `[context] instructions = ["latex"]` adds
  `~/.agents-context/instructions/latex.md`. Private, read-only instructions for one
  project go in `~/.agents-context/project-instructions/<project>.md`. Adding, removing
  or editing any instruction file (including `all.md`) now shows the restart notice.
- `[project] env = { KEY = "value" }` sets environment variables in every container of
  a project (or of a folder, in a group file). `ref_ro`, `data_ro` and `--ro` accept
  `project:<name>` (your repository of another project) and `agents:<name>` (its agent
  copy, without its private files), mounted read-only at `/ref/<name>` (`/data/<name>`
  in `data_ro`).
- Image layers can `include` other layers: their own parts are applied before the
  layer's own, e.g. `[webdocs] parent = "web"`, `include = ["docs"]` (see
  `examples/images/profiles.toml`). Layers that use `docs` get TeX Live mounted; the
  mounted folder now goes through the usual mount checks, so a TeX Live directly in your
  home folder is refused instead of exposing all of `$HOME`. Setup scripts keep their
  order with ten or more parts.
- Shared agent defaults: files in `~/.agents-context/agents/<agent>/` are copied into
  each project's agent config folder when missing (never replacing a file), e.g. a
  Claude status line; `codex/config.toml` becomes Codex's system config. Optional shared
  Claude login: a token from `claude setup-token` in
  `~/.local/share/agentbox/auth/claude.env` reaches only the claude containers.
  Rebuild images (`agentbox-build`) before using shared defaults.
- `agentbox rename <old> <new>` moves a project's agentbox state (agent copy, bridge,
  logins and conversations, private files, config) after you rename its repository
  folder, and updates the `agent` remote. Moving a repository to another folder of
  `~/Projects` needs no command. Project folders whose name cannot be a pod name (for
  example with spaces) or is reserved for an agentbox command now get a clear error.
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
