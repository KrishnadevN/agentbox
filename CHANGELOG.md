# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org);
before 1.0, minor versions may change the configuration format.

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
