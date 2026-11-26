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
- [Moving or renaming a project](#moving-or-renaming-a-project)
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
- **Git.** Agents commit as you (your global git name and email). agentbox passes none
  of your git credentials (SSH keys, tokens, credential helpers) into the sandbox, so
  they cannot push; you review and push from your own repository. Anything you hand them
  yourself, a read-only folder or an `env` value, is readable in full, secrets included
  (see `project:` references below).
- **Resources.** All agents together get your RAM and CPUs minus a reserve that you set,
  so your desktop stays usable. Thread variables (OpenMP, BLAS, numba) follow the limit.

## Install

You need Linux with cgroup v2, unprivileged user namespaces and a systemd user session.
The prep script installs the rest on Arch-based systems (Podman ≥ 5, passt, nftables,
Python ≥ 3.11, git, tmux, gVisor). On other distributions it tells you what is missing;
support for more distributions is welcome.

```
git clone https://github.com/KrishnadevN/agentbox ~/.agentbox
git -C ~/.agentbox checkout v0.2.0-beta.1          # a release; skip for the latest main
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
| Rename a project | see [Moving or renaming a project](#moving-or-renaming-a-project) |

Agents keep running when you close the terminal only if you started them inside tmux
(or similar) on the host. For long jobs, start tmux first and detach with `Ctrl-b d`.

### Logging in

You log in once per agent and project. Each agent's config folder (login, settings,
plugins, conversations) lives in its home for that project,
`~/.local/share/agentbox/home/<project>/<agent>/`. It is kept between runs and never
shared with another project, so an agent in one project cannot read another project's
conversations, and `/resume` lists only this project's. Only the Copilot token (and the
optional Claude token below) is shared.

- **Claude Code:** start it, type `/login`, open the link on your machine, paste the code.
  To log in once for all projects instead, create a long-lived token with
  `claude setup-token` (on any machine with Claude Code) and save it, readable only by
  you and without the token in your shell history (works from bash, zsh and fish; paste
  the token at the prompt):
  ```
  bash -c 'umask 077; f=~/.local/share/agentbox/auth/claude.env
    read -rsp "Token: " t && echo && [ -n "$t" ] &&
    printf "CLAUDE_CODE_OAUTH_TOKEN=%s\n" "$t" > "$f" && chmod 600 "$f"'
  ```
  Or write the file by hand: one line `CLAUDE_CODE_OAUTH_TOKEN=<token>`, no quotes, no
  `export`, and `chmod 600` it.
  Only the claude containers receive it, and it takes precedence over a `/login` in a
  project. It uses your subscription, like `/login`, but can only make model requests:
  claude.ai connectors and Remote Control are not available with it (`/login` in a
  session switches that session back). It lasts up to a year; revoke it in your
  claude.ai settings. The claude container of every project that runs Claude can read
  it, so one leak exposes your subscription everywhere until you revoke it. After
  adding, replacing or removing the file, restart running projects (`agentbox <project>
  restart`): until then they keep the old token, even a removed one. Codex and
  Antigravity have no such token for personal plans; log in once per project.
- **Codex:** turn on device-code login in your ChatGPT security settings. Then
  `agentbox <project> shell codex`, run `codex login --device-auth`, exit, and start
  `agentbox <project> codex`.
- **Antigravity:** start it, open the link, paste the code.
- **Copilot:** do not use `/login`. That token can also act on your repositories, so an
  agent could push with it. Instead, create a fine-grained token on your personal
  account with only the **Copilot Requests** permission, and save it the same way:
  ```
  bash -c 'umask 077; f=~/.local/share/agentbox/auth/copilot.env
    read -rsp "Token: " t && echo && [ -n "$t" ] &&
    printf "COPILOT_GITHUB_TOKEN=%s\n" "$t" > "$f" && chmod 600 "$f"'
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
instructions come on top of that:

| Where | Who sees it | Good for |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/` in the repository | everyone who clones it | project rules you are happy to publish |
| `~/.agents-context/projects/<project>/` | only your agents, writable | private notes and rules for one project |
| `~/.agents-context/instructions/all.md` and `<agent>.md` | only your agents, read-only | your personal rules for every project |
| `~/.agents-context/instructions/<module>.md`, listed in `[context] instructions` | only your agents, read-only | rules for some projects (LaTeX, a language, a workflow) |
| `~/.agents-context/groups/<folder>/.../group.md` | only your agents, read-only | rules for every project below a folder of `~/Projects` |
| `~/.agents-context/project-instructions/<project>.md` | only your agents, read-only | private rules for one project that agents must not change |

The read-only files are added to each agent's context file in this order: `all.md`,
`<agent>.md`, the modules in listed order, the folder files from the outermost folder
inward, the project file. For `~/Projects/research/Survey/Survey-paper` the folder files
are `groups/research/group.md`, then `groups/research/Survey/group.md`. List modules by
file name without `.md`, e.g. `[context] instructions = ["latex"]` in a group or project
file (`all`, `dev` and agent names are not module names; those files are added anyway).
A missing module is skipped with a warning. After adding, removing or editing any of
these files, the next `agentbox <project> <agent>` tells you to restart the project
(`agentbox <project> restart`); the low-level `agentbox-enter` does not check.

**Private project files.** Everything in `~/.agents-context/projects/<project>/` appears
in the sandbox at `/work/.agentbox/`, and each entry is linked into `/work` — so a private
`AGENTS.md` or `.claude/` folder there works as if it were part of the repository. The
links are excluded from git, so they don't end up in commits. If the repository already
has a file with the same name, agentbox leaves the repository's file alone and tells you;
the agent can still read the private one in `/work/.agentbox/`. Agents can write there
too (notes, plans, memory files), which makes it a good place for things that must not be
published.

**Shared agent defaults.** Settings you make in one project (a status line, preferred
options) stay in that project's config folder. To give every project the same start,
put files in `~/.agents-context/agents/<agent>/` (`claude`, `codex`, `agy`, `copilot`),
laid out like the agent's config folder (`~/.claude`, `~/.codex`, `~/.gemini`,
`~/.copilot`). On every launch, files that a project does not have yet are copied into
it; files that exist are never replaced, so changes made in a project stay (delete the
project's copy to get the default again). Each folder is visible, read-only, only to its
own agent. For Codex, `codex/config.toml` is not copied but read as Codex's system
config, below each project's own `config.toml`, so edits reach every project. Example:
`examples/agents/claude/` (a status line). Never put login files there
(`.credentials.json`, `auth.json`, Copilot's `config.json`, Antigravity's account
files): copies of a login log each other out. Creating or removing an agent's folder
needs a restart of running projects; adding files to an existing folder does not.
This needs images built with agentbox 0.2 or later (`agentbox-build`).

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

## Moving or renaming a project

**Moving** a repository to another folder of `~/Projects` (say from `research/` to
`teaching/`) needs no command: agentbox keeps everything under the project's name and
finds the folder anew on every call. The settings and instructions of the new folders
apply from the next start; `agentbox <project> restart` applies them to a running pod.

**Renaming** (for example a placeholder to `JournalName2027`):

1. `agentbox-down <old>`
2. rename the repository folder (you can move it at the same time)
3. `agentbox rename <old> <new>`
4. `agentbox <new>`

`agentbox rename` moves the agents' copy, the bridge, each agent's login and
conversations, the private project files and instructions, and
`~/.config/agentbox/projects/<old>.toml`, and points your repository's `agent` remote
to the new copy. It changes nothing if a pod for either name exists (stop it with
`agentbox-down <name>`), if any target already exists, if git cannot run, or if a name
cannot be used; don't start either name until it has finished.
It does not update references to the old name in other files (`project:<old>`,
`agents:<old>`), and it leaves the old systemd slice file in
`~/.config/systemd/user/`, which is harmless. Project names may use letters, digits,
`_`, `.` and `-` (not first), and a few words are reserved for agentbox commands; such
folders get an error that says so.

## Configuration

Settings are TOML files, read in this order (later ones win, command-line options win
over all):

| File | What it is for |
|---|---|
| `~/.agentbox/defaults.toml` | the package defaults — don't edit, override instead |
| `~/.config/agentbox/config.toml` | your defaults for every machine and project |
| `~/.config/agentbox/hosts/<hostname>.toml` | one machine: label, GPU, reserves, `tex_root` |
| `~/.config/agentbox/groups/<folder>/.../group.toml` | every project below a folder of `~/Projects`, outermost folder first |
| `~/.config/agentbox/projects/<project>.toml` | one project: image, agents, ports, datasets |

`examples/` has a starting point for each, including a project file that lists every
option with its default. A project without a file uses the defaults and you get a warning.

Group files mirror the folders above a project: `~/Projects/research/Survey/Survey-paper`
reads `groups/research/group.toml`, then `groups/research/Survey/group.toml`. They take
the same keys as project files, with two exceptions: the global reserves (`[resources]
reserve_*`, `memory_high_pct`, `tasks_max`) belong in the host file and are ignored with
a warning, and `tags` (for `agentbox list --tag`) is read only from the project file.
A list in a later file replaces the earlier list; lists are not merged. Tables such as
`env` are combined key by key, and the later file wins per key.

**Environment variables.** `[project] env = { KEY = "value" }` sets variables in every
container of the project (agents and dev). agentbox's own variables (`HOME`, `PATH`,
`AGENTBOX_*`, `GIT_CONFIG_GLOBAL`, the Copilot and Claude tokens) cannot be changed this
way; such keys are ignored with a warning. Every agent can read the values (so can
`podman inspect`), so don't put secrets there that you would not give the agents.

**Other projects, read-only.** Besides host folders, `ref_ro` and `data_ro` (and
`--ro` on the command line) accept two references, mounted read-only at `/ref/<name>`
(`/data/<name>` in `data_ro`):

- `project:<name>`: your repository of that project, as you have it in `~/Projects`:
  the whole working tree, including `.git`, uncommitted files and ignored files such as
  `.env`. Read-only does not stop agents from reading or uploading any of it, so don't
  reference a repository that holds secrets.
- `agents:<name>`: that project's agent copy (`~/.agents-projects/<name>`), with
  whatever its agents have written, committed or not. Its private files
  (`/work/.agentbox` there) are not included. Treat the content like anything agents
  write: this project's agents can read text placed there by the other project's agents.

For example, to work on a paper while agents in another project develop the Python
package it uses:

```toml
# ~/.config/agentbox/projects/Survey-paper.toml
[project]
ref_ro = ["agents:mypkg"]                  # or "project:mypkg" for your reviewed version
env    = { PYTHONPATH = "/ref/mypkg/src" }
```

`import mypkg` then uses the other project's current code. The mount is read-only, so
don't install the package in editable mode there, and don't write sandbox paths such as
`/ref/...` into the paper's `pyproject.toml` or `uv.lock`.

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
- A layer can also take the parts of other layers without building on them, with
  `include`. For a project that needs both web and docs tools:
  ```toml
  [webdocs]
  parent = "web"
  include = ["docs"]
  ```
  The included layers' own parts (not their parents) are applied first, in order, then
  the layer's own. A layer's parts are never applied twice in one image: including
  something the parent image already has is an error. Included parts are stored again
  in this image, so it is larger than one built on top. Layers that use `docs`, as
  parent or include, get TeX Live mounted. See `examples/images/profiles.toml`.

After changing a layer, rebuild it, the layers on top of it and the layers that include
it (`agentbox-build` alone rebuilds everything).

## What agentbox does not protect

Please read this before you hand an agent anything important.

- **Leaks over the internet.** Agents can reach any public website. An agent that has been
  tricked — by a web page, a README, an issue comment — can upload the project and its
  own login token. Keep secrets out of your projects and revoke tokens if something looks
  wrong.
- **Agents trust each other.** All agents of a project share `/work`. One can change a
  script that another, or you, will run later.
- **Projects you connect.** A `project:<name>` reference shows agents your whole
  repository, `.git`, `.env` and uncommitted files included. An `agents:<name>`
  reference lets one project's agents read what another project's agents wrote,
  including text meant to mislead them. A shared Claude token (`claude.env`) is
  readable in the claude container of every project that runs Claude.
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
- `agentbox --version` prints the installed version. To update agentbox, read the
  upgrade steps for the new version in `CHANGELOG.md` first, then
  `git -C ~/.agentbox fetch --tags && git -C ~/.agentbox checkout v<version>` (or
  `git pull` if you follow main).

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
lib/        shell helpers, config merging (cfg.py), project discovery (projects.py),
            image layers (images.py), rename (rename.py)
images/     profiles.toml and one folder per layer
scripts/    host preparation, check suite, TeX Live installer
examples/   config, host, group, project, instruction and agent-default examples
tests/      unit tests (python3 -m unittest discover -s tests)
docs/       roadmap
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

