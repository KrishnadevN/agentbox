# agentbox

[![License: GPL v3+](https://img.shields.io/badge/License-GPLv3%2B-blue.svg)](LICENSE)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-lightgrey.svg)
![Status: early](https://img.shields.io/badge/status-early-orange.svg)

agentbox lets you run coding agents — Claude Code, Codex CLI, Antigravity CLI and
GitHub Copilot CLI — with all permission prompts turned off, without giving them your
machine. Each project gets its own sandbox. The agents can install packages, run builds
and tests, start servers and commit, but they cannot read your home folder, push to
GitHub, reach your local network, or take the whole machine down with a runaway job.

It is built from ordinary parts: rootless Podman, gVisor, nftables and systemd. There
is no daemon and no service to run; a few shell scripts set things up and start pods.

## Why I built this

I do research and write a lot of code with agents: Python packages, simulations that
run for days, LaTeX manuscripts, a website. Approving every command by hand stopped
being practical, but letting an agent run freely on the machine that holds my SSH keys,
my papers and my lab's network was not an option either.

I wanted something that fit the way I already work: agents in the terminal, one tmux
window each, on a laptop and on a workstation that run different Linux distributions
(an Arch-based one and Fedora Atomic). I wanted to keep using my subscription logins,
read every line of the tool that guards my machine, and have each project carry its
own settings: which image, which datasets, which ports, which agents. That combination
didn't exist, so agentbox is my answer to it — shell scripts around Podman and gVisor,
plus the project automation I kept doing by hand.

If you work in a similar way, it may suit you too. If not, look at the
[alternatives](#alternatives) first; one of them may be a better fit.

> [!WARNING]
> **agentbox is developed with the help of coding agents, and comes with no guarantees.**
> I use it every day on my own machines, every change is reviewed by me before it is
> committed, and the check suite tests the safety-critical parts. Still, it is young,
> it is tested on few systems (Arch-based Linux with Podman 6 so far), and a sandbox
> tool that is wrong can give you a false sense of safety. Read the code before you
> trust it — it is a few shell scripts and small Python helpers, written to be read —
> run `scripts/agentbox-check.sh` on your machine, and read
> "[What agentbox does not protect](#what-agentbox-does-not-protect)".
> You are responsible for what you run with it. See also the [License](#license):
> the software is provided without any warranty.

## Contents

- [How it works](#how-it-works)
- [Install](#install)
- [Your first project](#your-first-project)
- [Working with agent commits](#working-with-agent-commits)
- [Telling agents what to do](#telling-agents-what-to-do)
- [Configuration](#configuration)
- [Image layers](#image-layers)
- [What agentbox does not protect](#what-agentbox-does-not-protect)
- [Alternatives](#alternatives)
- [Maintenance](#maintenance) · [Troubleshooting](#troubleshooting) · [Repository layout](#repository-layout)
- [Contributing](#contributing) · [License](#license)

## How it works

Your own repository stays where it is, for example `~/Projects/website`. agentbox makes
a copy for the agents in `~/.agents-projects/website` and starts a pod for it:

```
~/Projects/website            your repository: your editor, your git, your pushes
        │  agentbox website sync      your commits → a read-only "upstream" for the agents
        ▼
~/.agents-projects/website    the agents' copy, mounted at /work in the sandbox
        │  agentbox website fetch     their commits → agent/* branches in your repository
        ▼
pod "ab-website"              one network namespace with the egress rules
 ├── claude    sees only Claude's login
 ├── codex     sees only Codex's login
 ├── agy       sees only Antigravity's login
 ├── copilot   sees only its Copilot token
 └── dev       no logins: servers, builds, your own shell
```

Inside the sandbox:

- **Kernel.** Agents run on gVisor, a kernel written in user space. Most kernel exploits
  do not reach your real kernel. You can switch a project to plain containers (`crun`)
  when gVisor is too slow or incompatible.
- **Files.** Only the project copy, the folders you list as read-only, the agent's own
  config folder for this project, and shared package caches. No home folder, no SSH
  keys, no keyring.
- **Network.** The public internet works. Your LAN, your Tailscale tailnet, services on
  your machine's localhost, link-local addresses and outgoing SSH are blocked. Name
  lookups go through your host's own resolver (via Podman's DNS forwarder), so DNS works
  on networks that block outside DNS servers; agents can look up internal names, but not
  connect to them.
- **Git.** Agents commit as you (your global git name and email), but they have no
  credentials, so they cannot push. You review and push from your own repository.
- **Resources.** All agents together get your RAM and CPUs minus a reserve that you set,
  so your desktop stays usable. Thread variables (OpenMP, BLAS, numba) follow the limit.

## Install

You need Linux with cgroup v2, unprivileged user namespaces and a systemd user session.
The prep script installs the rest on Arch-based systems (Podman ≥ 5, passt, nftables,
Python ≥ 3.11, git, tmux, gVisor). On other distributions it tells you what is missing;
support for more distributions is welcome.

```
git clone https://github.com/<owner>/agentbox ~/.agentbox
~/.agentbox/scripts/agentbox-prep.sh --dry-run    # shows what it would change
~/.agentbox/scripts/agentbox-prep.sh              # asks for sudo where needed
```

If the script says "delegation changed", log out completely, log in again, and run it
once more. Then open a new terminal and build the images and install the agent CLIs:

```
agentbox-build            # takes a few minutes the first time
agentbox-update-tools
```

Last, run the checks. Everything should say PASS:

```
~/.agentbox/scripts/agentbox-check.sh
~/.agentbox/scripts/agentbox-check.sh --runtime crun
```

**Shell integration.** The prep script links the fish version automatically. For bash
or zsh, add one line to your rc file (agentbox never edits it for you):

```
source ~/.agentbox/shell/agentbox.bash     # in ~/.bashrc
source ~/.agentbox/shell/agentbox.zsh      # in ~/.zshrc, after compinit
```

This puts the commands on your PATH, completes project names from any folder, and
turns off git inside `~/.agents-projects` (see [below](#working-with-agent-commits)).

**LaTeX.** For writing projects, `scripts/agentbox-install-texlive.sh` installs TeX Live
from TUG once. Your host and the containers share that single copy. Afterwards, set
`tex_root` in your host file (see [Configuration](#configuration)).

## Your first project

Any git repository in `~/Projects` with at least one commit works, also in subfolders up
to four levels deep, such as `~/Projects/research/Survey/Survey-paper`. The project's name
is the repository's folder name (`Survey-paper`), so names must be unique: if two
repositories share a name, agentbox lists both paths and refuses that name until you
rename one. Hidden folders are skipped, and agentbox does not look inside a repository
(nested repositories and submodules are not projects).

agentbox does not follow symlinks in `~/Projects`, so each project has exactly one path:
a symlinked folder is not found. A project needs its own `.git` folder, so linked
worktrees (`git worktree add`) are not projects either: they share their main
checkout's remotes and branches. Keep real repositories in `~/Projects` and use the main
checkout. `~/Projects` itself may be a symlink.

```
agentbox website claude
```

The first time, this creates the agents' copy, starts the pod, and opens Claude Code in
its container. Other commands:

| What you want | Command |
|---|---|
| Start an agent | `agentbox website claude` (or `codex`, `agy`, `copilot`) |
| A shell without any logins | `agentbox website` or `agentbox website shell` |
| A shell in an agent's container | `agentbox website shell claude` |
| Use plain containers this time | `agentbox website claude --runtime crun` |
| Show a dataset to the agents (read-only, this run) | `agentbox website claude --ro ~/Data/survey` |
| Limit this project | `agentbox website claude --mem 32G --cpus 8` |
| See what the network rules refused | `agentbox website blocked` |
| Apply changed settings | `agentbox website restart` |
| Stop it (files and logins stay) | `agentbox website down` |
| Stop everything | `agentbox down-all` |
| List projects and pods (a tree by folder) | `agentbox list` |
| Only one folder, or one tag | `agentbox list research`, `agentbox list --tag paper` |

Agents keep running when you close the terminal only if you started them inside tmux
(or similar) on the host. For long jobs, start tmux first and detach with `Ctrl-b d`.

### Logging in

You log in once per agent and project. Each agent's config folder (login, settings,
plugins, conversations) lives in its home for that project,
`~/.local/share/agentbox/home/<project>/<agent>/`. It is kept between runs and never
shared with another project, so an agent in one project cannot read another project's
conversations, and `/resume` lists only this project's. Only the Copilot token is shared.

- **Claude Code:** start it, type `/login`, open the link on your machine, paste the code.
- **Codex:** turn on device-code login in your ChatGPT security settings. Then
  `agentbox <project> shell codex`, run `codex login --device-auth`, exit, and start
  `agentbox <project> codex`.
- **Antigravity:** start it, open the link, paste the code.
- **Copilot:** do not use `/login`. That token can also act on your repositories, so an
  agent could push with it. Instead, create a fine-grained token on your personal
  account with only the **Copilot Requests** permission, and save it:
  ```
  printf 'COPILOT_GITHUB_TOKEN=%s\n' 'github_pat_...' > ~/.local/share/agentbox/auth/copilot.env
  chmod 600 ~/.local/share/agentbox/auth/copilot.env
  ```
  Only the copilot container receives it.

### Viewing a website

List the port in the project file (`publish = ["5173"]`, see the examples), start the dev
server in the dev container with `--host 0.0.0.0`, and open `http://127.0.0.1:5173` on your
machine. Ports are always bound to 127.0.0.1, never to your network. To share a page with
other machines, put something you control in front of it, such as `tailscale serve`.

## Working with agent commits

The agents work in `~/.agents-projects/<project>`. **Treat that folder as untrusted.**
An agent can write git settings there that run a program the next time *anyone* runs
git in that folder — including your shell prompt, which runs `git status` for you, or
your editor's git panel. So:

- Don't open `~/.agents-projects/*` in an editor with git support, and don't run git
  there. The shell integration turns git off in that folder for exactly this reason.
  Looking at files (PDFs, images, a built site) is fine.
- Bring the agents' work into your own repository instead. Fetching is safe: git does
  not run anything from the repository it fetches from.

A typical round:

```
agentbox website fetch                 # agent commits appear as agent/* branches
cd ~/Projects/website
git log --oneline main..agent/main     # what did they do?
git diff main...agent/main             # read the changes
git merge agent/main                   # or cherry-pick, or rebase — your call
git push
```

Review changes to build files and scripts (`Makefile`, `package.json` scripts,
`pyproject.toml`, CI files, `.envrc`) with extra care before you run anything from
them on your machine.

To give the agents your latest commits:

```
cd ~/Projects/website && git commit ...
agentbox website sync                  # updates their read-only "upstream"
```

Then tell the agent to run `git fetch upstream` and merge or rebase. Agents are already
told in their context file that this is how it works.

## Telling agents what to do

agentbox writes a small context file for every agent: which machine it is on, its limits,
how git and the network work in the sandbox, and both your git identity and its own. Your
instructions come on top of that, from three places:

| Where | Who sees it | Good for |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/` in the repository | everyone who clones it | project rules you are happy to publish |
| `~/.agents-context/projects/<project>/` | only your agents, writable | private notes and rules for one project |
| `~/.agents-context/instructions/all.md` and `<agent>.md` | only your agents, read-only | your personal rules for every project |

**Private project files.** Everything in `~/.agents-context/projects/<project>/` appears
in the sandbox at `/work/.agentbox/`, and each entry is linked into `/work` — so a private
`AGENTS.md` or `.claude/` folder there works as if it were part of the repository. The
links are excluded from git, so they don't end up in commits. If the repository already
has a file with the same name, agentbox leaves the repository's file alone and tells you;
the agent can still read the private one in `/work/.agentbox/`. Agents can write there
too (notes, plans, memory files), which makes it a good place for things that must not be
published.

**Skills.** Put skills in `~/.agents-context/skills/<name>/SKILL.md`. Every agent sees
them in its own personal skills folder (`~/.claude/skills`, `~/.agents/skills`, ...),
read-only by default. You can make them writable with `[context] skills = "rw"`, but then
an agent in one project can change a skill that agents in every other project use.

**Commit conventions.** agentbox never rewrites commits. If you want agents to add a
`Co-authored-by` trailer, commit in a certain style, or use their own identity, say so
in your instructions — for example in `~/.agents-context/instructions/all.md`:

```markdown
## Commits
Write small commits with clear messages. Add a trailer
`Co-authored-by: <your agentbox identity>` to each commit.
```

Agent CLIs may add their own trailer by default (Claude Code does); change that in the
CLI's settings if you don't want it.

`~/.agents-context` is just a folder. Make it a private git repository if you want to
sync it between machines; never make it public, since it holds your private notes.

## Configuration

Settings are TOML files, read in this order (later ones win, command-line options win
over all):

| File | What it is for |
|---|---|
| `~/.agentbox/defaults.toml` | the package defaults — don't edit, override instead |
| `~/.config/agentbox/config.toml` | your defaults for every machine and project |
| `~/.config/agentbox/hosts/<hostname>.toml` | one machine: label, GPU, reserves, `tex_root` |
| `~/.config/agentbox/projects/<project>.toml` | one project: image, agents, ports, datasets |

`examples/` has a starting point for each, including a project file that lists every
option with its default. A project without a file uses the defaults and you get a warning.

Keep `~/.config/agentbox` out of reach of agents — it decides what the sandbox may do,
so agentbox never mounts it. A project repository can contain an `.agentbox-hint.toml`,
but it can only make things stricter (go offline, force gVisor), because agents can edit it.

Folder locations can be changed with environment variables: `AB_PROJECTS` (default
`~/Projects`), `AB_AGENTS` (`~/.agents-projects`), `AB_CONTEXT` (`~/.agents-context`),
`AB_CONFIG` (`~/.config/agentbox`) and `AB_STATE` (`~/.local/share/agentbox`).

## Image layers

Each project uses one image ("profile"). The included ones build on each other:

| Profile | Adds |
|---|---|
| `base` | shell tools, git, Node LTS, and the file tools agents reach for: poppler (`pdftotext`, `pdfinfo`), qpdf, Ghostscript, ImageMagick (with `magick`), exiftool, pandoc, sqlite3, 7-zip, ripgrep, fd, jq, shellcheck |
| `python` | compilers, OpenBLAS, uv |
| `web` | pnpm and the system libraries for headless Chromium (Playwright) |
| `docs` | Typst, fonts, and TeX Live mounted from the host |

A layer is a folder in `images/` with up to four optional parts: `packages.txt` (apt
packages), `files/` (copied into the image), `setup.sh` (run as root) and `env.txt`
(`KEY=VALUE` lines). `images/profiles.toml` says which layer builds on which.

You can extend this without touching the package. In `~/.config/agentbox/images/`:

- `base/packages.txt` adds packages to the base layer (same for any layer name).
- A new folder plus an entry in `~/.config/agentbox/images/profiles.toml` adds a layer:
  ```toml
  [julia]
  parent = "python"
  ```
  Build it with `agentbox-build julia` and use it with `profile = "julia"`.

After changing a layer, rebuild it and the layers on top of it (`agentbox-build` alone
rebuilds everything).

## What agentbox does not protect

Please read this before you hand an agent anything important.

- **Leaks over the internet.** Agents can reach any public website. An agent that has been
  tricked — by a web page, a README, an issue comment — can upload the project and its
  own login token. Keep secrets out of your projects and revoke tokens if something looks
  wrong.
- **Agents trust each other.** All agents of a project share `/work`. One can change a
  script that another, or you, will run later.
- **`crun` shares your kernel.** Projects that use it give up the gVisor layer.
- **Shared caches.** uv, npm and pnpm caches are shared between projects. Use lockfiles.
- **The agent CLIs themselves** are installed with their vendors' official installers,
  in a separate container without your projects or logins.
- **gVisor networking** runs in host-network mode inside the pod's own network namespace,
  which rootless gVisor requires. The egress rules apply there.

## Alternatives

agentbox is one way to do this. Depending on what you need, another tool may serve you
better:

- **[Docker Sandboxes](https://docs.docker.com/ai/sandboxes/)** puts each agent session
  in its own microVM with its own kernel and Docker daemon. A proxy on the host enforces
  network rules and adds credentials to requests, so even subscription logins never enter
  the sandbox. It runs on macOS, Windows and Linux (officially Ubuntu), needs a Docker
  account and KVM, and lets agents build and run containers. If you are on one of those
  platforms and want the strongest boundary with the least setup, start there. Check its
  defaults: SSH agent forwarding is on, which lets the agent use your SSH keys.
- **[NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell)** focuses on policy: network
  access is denied by default and granted per destination and program, and credentials are
  replaced by placeholders. Its credential model is built around API keys.
- **The agents' own sandboxes** (Claude Code, Codex and Antigravity all have one) limit
  what individual commands can do. They are useful when you approve actions yourself;
  their makers recommend an outer sandbox for fully autonomous use.

Where agentbox fits: Linux only, rootless, no account and no KVM requirement, works on
Arch and Fedora Atomic, open internet by default with your local network blocked, your
own image layers and per-project settings, and a code base small enough to read.

## Maintenance

- Agent CLIs (and npm) update themselves before launch when they are older than 12 hours.
  `agentbox-update-tools` does it now.
- After a system update that touches the kernel, Podman, passt, systemd or gVisor, run
  the check suite again.
- Update gVisor with `agentbox-prep.sh --update-runsc`, the images with `agentbox-build`.
  For reproducible builds, pin the base image digest in `images/profiles.toml`.
- Update TeX Live with `agentbox-install-texlive.sh --update`.
- `agentbox --version` prints the installed version; see `CHANGELOG.md` for changes.

## Troubleshooting

| What you see | What to do |
|---|---|
| A gVisor container fails with a cgroup error | agentbox retries without `--cgroups=no-conmon`; then check section 8 of the check suite |
| "processes outside agents.slice" | the caps don't apply to those processes; use `--runtime crun` and open an issue |
| A LAN, tailnet or host test says reachable | stop using agentbox on that machine and open an issue with the output |
| New files in `/work` belong to a number instead of you | don't add `--user` or `--userns`: agents must run as container root, which is you |
| The dev server doesn't reload | set `dev_runtime = "crun"` in the project file: separate gVisor sandboxes don't share file events |
| Chromium or Playwright fails | run it in the dev container with `dev_runtime = "crun"` |
| Name lookups hang in the sandbox, logins fail with "error sending request" | DNS: keep the default `dns = ["169.254.1.1"]` (Podman's forwarder to your host's resolver); public resolvers are often blocked on institutional networks |
| A website fails in the check | if it also fails from your machine, it's your network, not the sandbox |

## Repository layout

```
bin/        commands: agentbox, agentbox-up/-down/-enter/-build/-update-tools/-new-worktree
lib/        shell helpers, config merging (cfg.py), image layers (images.py)
images/     profiles.toml and one folder per layer
scripts/    host preparation, check suite, TeX Live installer
examples/   config, host and project examples
shell/      bash, zsh and fish integration
net/        egress rules        templates/   agent context file
config/     Podman entry for gVisor
```

## Contributing

Bug reports are very welcome, especially from distributions and setups I can't test.
Please open an [issue](../../issues) and include the output of `scripts/agentbox-check.sh`,
your distribution, kernel, Podman and gVisor versions.

Pull requests are welcome too, with one request: keep agentbox small. It is meant to stay
a set of readable scripts around Podman and gVisor for terminal agents, not a platform.
Support for more distributions, fixes, and checks are the most useful contributions. Big
features (GUIs, cloud runs, a daemon) are probably better served by the tools under
[Alternatives](#alternatives), and I may decline them for that reason. Before you start
something large, open an issue so we can talk about it first.

For pull requests: run `scripts/agentbox-check.sh` (both runtimes if you touched the
sandbox) and `shellcheck`, keep changes focused, and say if an agent wrote part of it —
that's fine here, as long as you have reviewed it.

**Security problems** — a way out of the sandbox, around the network rules, or to host
files or credentials — should not go into a public issue. See [SECURITY.md](SECURITY.md).

## License

agentbox is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE).

It drives other programs (Podman, gVisor, nftables, systemd, the agent CLIs) but does not
include or redistribute them; each keeps its own license.

