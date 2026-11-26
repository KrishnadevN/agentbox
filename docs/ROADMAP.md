# Roadmap

Ordered by priority. One item = one commit (or a short series if the item says so).
Each milestone becomes a minor release; publish `-beta.N` tags while testing.
Read `AGENTS.md` first. "Verify" marks facts that must be checked against the current
tool version before relying on them.

Status: `[ ]` open · `[~]` in progress · `[x]` done

---

## 0.2.0 — Nested projects and composable images (high)

### [x] 1. Per-project agent config folders (privacy fix)

Problem: each agent's config folder (`auth/<agent>`) was shared by all projects, and the
working directory is `/work` everywhere, so conversations, history, paste caches and
memories of every project landed in the same place: `/resume` mixed projects,
`--continue` could pick up another project's conversation, and an agent in project A
could read project B's transcripts.

Design (decided): the whole config folder is per project. It lives in the agent's home,
which already exists once per project and agent (`home/<project>/<agent>`); the shared
`auth/<agent>` mounts are gone. Listing per-project paths inside a shared folder was
tried and rejected: the CLIs keep adding files, rewrite files by rename, and keep SQLite
side files and locks next to them.
- Claude Code, Codex and Antigravity log in once per project (their native flows).
  Copilot keeps the shared `auth/copilot.env` token (Copilot Requests only).
- Pods carry `agentbox.layout=2`; `agentbox-up` and `agentbox-enter` refuse a running pod
  without it and ask for a restart.
- Old `auth/<agent>/` folders are left alone; the CHANGELOG says to delete them by hand.
- Later, if per-project logins become a nuisance: an opt-in shared Claude token
  (`claude setup-token`).

Acceptance: check suite — a marker in project A's config folder is not visible in a second
project, each agent's instruction file is in place in both, and both launcher paths
refuse a running pod without the layout label.

### [x] 2. Nested project discovery

Goal: projects may live at any depth (≤ 4) under `~/Projects`, e.g.
`research/ProjectName/ProjectName-manuscript`. Nothing is stored separately, so nothing
goes out of sync.

Design (decided):
- A project is a folder with its own `.git` **folder**. Walk `$AB_PROJECTS` to depth 4 and
  **stop descending** at any `.git` (a `.git` file or symlink, as in linked worktrees, is
  a boundary but not a project: it shares another checkout's remotes). Skip hidden
  folders; do not follow symlinks (one path per project). Implement in Python
  (`lib/projects.py`, stdlib only).
- Project name = the repo folder's own name (basename). It stays the key everywhere:
  `~/.agents-projects/<name>` (flat), `~/.config/agentbox/projects/<name>.toml`, pod
  `ab-<name>`, `~/.agents-context/projects/<name>/`.
- Two or more repos with the same name → refuse to start, list all their paths.
- Path-derived metadata: `category` = first path component below `~/Projects` (if depth
  > 1), `group` = parent folder name (if depth ≥ 3). Optional `tags = [...]` in the
  project config.
- Replace every `$AB_PROJECTS/$p` with a lookup (`ab_project_path <name>` in bash, a
  function in `cfg.py`). Places: `bin/agentbox` (existence check, `fetch`, `sync`, `list`),
  `bin/agentbox-new-worktree`, `lib/cfg.py` (hint file, working-tree warning),
  `scripts/agentbox-check.sh` (self-test project), the three shell completions.
- `agentbox list` shows a tree (category → group → repo) with columns config / copy / pod.
  `agentbox list <category|group>` and `agentbox list --tag <t>` filter it.
- Completion calls one fast helper (`agentbox __projects`) instead of globbing.

Acceptance:
- `tests/test_projects.py` (unittest, temp dirs): depth limit, pruning at `.git`, `.git`
  file or symlink is no project, symlinked folders not followed, nested repo ignored,
  duplicate detection, category/group derivation.
- Existing flat projects keep working unchanged, except symlinked folders and linked
  worktrees (documented in the CHANGELOG).
- Check suite passes; CI runs the unit tests.

### [x] 3. Group configuration and group instructions

- Files mirror the folders above a project, each with a fixed name, so same-named folders
  in two categories stay apart. Only a folder literally named `group.toml` or `group.md`
  can conflict with its parent's file in the mirrored tree; agentbox then treats the
  blocked file as absent (only regular files are read). `research/Survey/Survey-paper` reads `groups/research/group.toml`, then
  `groups/research/Survey/group.toml`.
- Merge order: package defaults < `config.toml` < `hosts/<host>.toml` <
  `groups/<a>/group.toml` < `groups/<a>/<b>/group.toml` < ... < `projects/<name>.toml` <
  hint < CLI. Group files take project keys; the global cap (`[resources] reserve_*`,
  `memory_high_pct`, `tasks_max`) is ignored there with a warning; `tags` stay
  project-only.
- Folder instructions: `~/.agents-context/groups/<a>/group.md`, `.../<a>/<b>/group.md`.
- Instruction modules: `[context] instructions = ["name", ...]`, only from trusted TOML
  (never the hint), appends `~/.agents-context/instructions/<name>.md`. Names are plain
  file names (no `/`, no leading `.`; not `all`, `dev` or an agent name); missing: warn
  and skip.
- Private project instructions: `~/.agents-context/project-instructions/<project>.md`
  (its own folder, never mounted).
- Context file order: sandbox facts, `all.md`, `<agent>.md`, modules, folder files outer
  first, project file. Instruction file contents are part of the config hash, so edits
  show the restart notice.

Acceptance: example files in `examples/groups/` and an example module in
`examples/instructions/`; README section; cfg.py tests for the merge order, the module
list and the hash; a check-suite test for folder and project instructions.

### [x] 4. Per-project environment and project references

- `[project] env = { KEY = "value" }` → `-e KEY=value` for all containers of the project.
  Reject `AGENTBOX_*`, `HOME`, `PATH` (warn and ignore); values are plain strings.
- `ref_ro`/`data_ro` entries may use `agents:<name>` (that project's agent copy,
  `~/.agents-projects/<name>`) and `project:<name>` (the trusted repo, via discovery).
  Mount points stay `/ref/<basename>`.
- Use case to document: live development of a Python package from another project via
  `env = { PYTHONPATH = "/ref/<pkg>/src" }` (no editable install into a read-only mount;
  don't write sandbox paths into the research repo's `pyproject.toml`/`uv.lock`).

Acceptance: config tests; check suite case that an env var arrives and an `agents:` mount
is read-only.

### [x] 5. Layer `include`

- `images/profiles.toml` (and the user's) may set `include = ["docs", ...]` on a layer.
  The build copies the included layers' own parts (packages, files, setup, env — not their
  parents) into this layer, in order, before the layer's own parts. Detect cycles.
- Example in `examples/`: `[webdocs] parent = "web"`, `include = ["docs"]`.
- Document the trade-off: included parts are stored again in this image.

Acceptance: `images.py plan` test with include + cycle; build of the example succeeds.

### [x] 6. Shared agent defaults

With per-project config folders (item 1), settings made in one project (a status line,
preferred options) do not reach the others.
- Files in `~/.agents-context/agents/<agent>/` (e.g. `claude/statusline.sh`,
  `claude/settings.json`, `codex/config.toml`) are copied into that agent's config folder
  of a project when the file is missing there; existing files are never overwritten.
  The folder is mounted read-only into that agent's container only, and the copy runs
  inside the container (the config folder is agent-writable), like the Codex defaults
  today.
- Verify first how each CLI supports user-wide defaults (e.g. Codex
  `/etc/codex/config.toml`, Claude Code managed settings, Antigravity, Copilot) and
  prefer a native read-only layer where one exists and fits.
- Logins are never copied: Claude Code and Codex rotate refresh tokens, so copies would
  log each other out. Opt-in shared Claude login instead: if `auth/claude.env` exists
  (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`), the claude container gets it with
  `--env-file`, exactly like `copilot.env`; without it, `/login` per project keeps
  working. README: the token lasts up to a year and is revoked in claude.ai settings.
  Codex and Antigravity keep one login per project (no long-lived token for personal
  plans).

Acceptance: check suite — a default file appears in a new project; an existing file is
kept unchanged; with `claude.env`, the token reaches only the claude container. README
section.

### [x] 7. `agentbox rename <old> <new>`

For renames like a placeholder → `JournalName2027`. With the pod removed, the user renames
the repo folder first; then this command moves `~/.agents-projects/<old>`, the bridge,
`ctx/`, `home/`, `~/.agents-context/projects/<old>`, `project-instructions/<old>.md`,
`projects/<old>.toml`, and updates the trusted repo's `agent` remote. Refuses while a pod
for either name exists and never stops one; refuses if any target exists. Each move is one
rename that never copies or overwrites (no traversal inside agent-writable folders). The
old slice file is left for item 15. Moving between folders needs no command.

### [ ] 8. Release 0.2.0

README (layout, groups, env, include, rename), CHANGELOG, examples; beta tag, test on the
laptop, then `v0.2.0`.

---

## 0.3.0 — Agent workflow (medium)

### [ ] 9. Documentation site and a shorter README

- Markdown sources in `docs/`, published to GitHub Pages by a GitHub Actions workflow.
  Choose a static site generator with few dependencies; verify that it is actively
  maintained at the time (candidates: MkDocs with Material, Zensical) and say in the
  commit why you chose it.
- Pages: getting started; how it works and the security model (including what agentbox
  does not protect); daily workflow (below); configuration reference (all files, merge
  order, every option); image layers; agent context and instructions (where each file
  goes, what loads automatically); logins per agent; troubleshooting; maintenance and
  updating; developing agentbox (link `AGENTS.md` and the roadmap).
- The daily workflow page covers: start agents; `agentbox <p> fetch`; review (`git log` /
  `git diff` against `agent/*`); merge; sign agent commits before pushing with
  `git rebase --force-rebase -S origin/main` and check with `git log --show-signature`;
  push; `agentbox <p> sync`; agents then run `git fetch upstream && git rebase
  upstream/main` (signing changes commit IDs, and the rebase drops the duplicates).
- README: what it is, why, a short quick start, the warning box, alternatives, license,
  and links to the docs. Everything else moves to the docs.

Acceptance: the site builds in CI on every push and deploys from `main`; README links
work; no content is lost in the move.

### [ ] 10. Pass arguments to the agent

`agentbox <p> claude -- --continue` → everything after `--` is appended to the agent
command. Same for `codex`, `agy`, `copilot`.

### [ ] 11. Handoff folder and review-workflow instructions

- Create `/work/.agentbox/handoff/` (inside the private project folder); mention it in the
  context template.
- `examples/instructions/review-workflow.md`, for users to copy to
  `~/.agents-context/instructions/all.md` and adapt:
  - roles: implementer, reviewer;
  - `STATUS.md` with fixed fields: `state` (planning | waiting-review | revising |
    approved-by-agents | needs-human | implementing | waiting-code-review | done),
    `owner`, `task`, `round`, `updated`;
  - files: `plan-NNN.md`, `review-NNN-rK.md`, `discussion.md`;
  - review levels: `must` (blocks) / `should` / `nit`; approve when no `must` is left;
    findings that contradict the user's guidelines are not `must`;
  - at most 3 rounds, then `needs-human`; the human confirms before implementation;
  - commit trailers in one final paragraph: `Implemented-by:`, `Reviewed-by:`,
    `Co-authored-by:`; agents report their own current model name.

### [ ] 12. Headless runs: `agentbox <p> run <agent> [--resume] "<prompt>"`

- New config per agent: `headless` and `headless_resume` command lists.
  Defaults to verify: Claude `claude -p --dangerously-skip-permissions` (+ `--continue`);
  Codex `codex exec --dangerously-bypass-approvals-and-sandbox` (resume: `codex exec resume
  --last`). Agy and Copilot: verify their headless flags; leave empty if unknown.
- Runs in the agent's own container (`podman exec` without TTY), output also appended to
  `/work/.agentbox/handoff/run-<agent>.log`.

### [ ] 13. `agentbox <p> review [branch]`

Fetch, then in the trusted repo: commit list and `diff --stat` of `agent/<branch>` against
the default branch (detect `main`/`master`). Read-only; merging stays manual.

### [ ] 14. Notifications

Defaults written by prep into the sandbox login folders (only if not set): Claude terminal
bell, Codex terminal notifications (verify setting names). README: kitty shows them; in
tmux set `monitor-bell on` and `allow-passthrough on`. No D-Bus, no host sockets.

### [ ] 15. `agentbox doctor` and `agentbox clean <p>`

- `doctor`: versions (agentbox, podman, runsc, CLIs), paths agentbox writes outside the
  package with sizes, stale slices/pods/state for projects that no longer exist, Podman
  storage use.
- `clean <p>`: with the pod down, remove that project's agent copy, bridge, `ctx/`,
  `home/`, slice file (asks first; never touches `~/Projects`, never touches
  `~/.agents-context` without `--context`).

### [ ] 16. Image name prefix for development

`AB_IMAGE_PREFIX` (default `sbx`) used by `images.py`, `cfg.py`, `agentbox-update-tools`, so
a development checkout can build and test `localhost/sbxdev-*` without replacing the images
real projects use.

### [ ] 17. Release 0.3.0

---

## 0.4.0 — Workstation and tmux (low)

### [ ] 18. Fedora Atomic (Kinoite/Silverblue) support in prep

- Detect rpm-ostree; Podman is preinstalled; install missing pieces by layering only if
  needed; gVisor tarball into `/usr/local/bin` (writable on ostree).
- SELinux: shared mounts need `:z`; private ones `:Z`; never relabel `$HOME` itself.
  Verify how runsc handles labels; `setsebool -P container_use_devices=true` for GPU.
- Check suite must pass on Kinoite.

### [ ] 19. NVIDIA GPU tier

Host `gpu = "nvidia-cdi"`; project `gpu = "optional" | "required"`. With a GPU: `crun` +
`--device nvidia.com/gpu=all` for the containers that need it (runsc + nvproxy stays an
experiment). Optional `cuda` layer for `nvcc`. Check: `nvidia-smi` and
`torch.cuda.is_available()` in the container; CPU fallback on hosts without GPU.

### [ ] 20. tmux layout

`agentbox <p>` (no action) opens or re-attaches tmux session `ab-<p>`: window `host`
(trusted repo folder, plain host shell), one window per agent, `dev`. `monitor-activity`
on agent windows. Scripts never `send-keys` agent-written content.

### [ ] 21. Release 0.4.0

---

## Later (lower)

### [ ] 22. `agentbox <p> loop` — automated implement/review rounds

Host-side, after the protocol of item 11 has worked manually for a while. Reads `STATUS.md`
strictly (allowed values only, size cap), sends only fixed prompts via `run --resume`,
stops at `approved-by-agents`, `needs-human` or the round limit.

### [ ] 23. Per-agent worktrees (opt-in)

`worktrees = true`: each agent container gets its own git worktree/branch of the agent
copy, created inside the sandbox so paths match. Only if parallel agents become common.

---

### [ ] 24. API keys, other model providers and more agent CLIs

- Credential files per agent: `auth/<agent>.env` reaches only that agent's container
  with `--env-file` (as `claude.env` and `copilot.env` do today), for API keys
  (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ...) and provider settings, e.g. Claude Code on
  Amazon Bedrock (`CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION`, AWS credentials) or Vertex
  AI. Their names are reserved in `[project] env`. Decide in the plan whether a project
  can choose other credentials than the global ones.
- More agent CLIs, verified at the time (e.g. OpenCode, Pi): install and update in
  `agentbox-update-tools`, a config folder per project, an instruction file, an entry in
  the known agents.
- README: keys and cloud credentials spend money and an agent can read and use them
  outside its CLI; recommend scoped, limited keys (provider spend limits; an AWS policy
  that only allows model invocation, short-lived credentials). Cloud CLI folders
  (`~/.aws`, ...) are never mounted.

Acceptance: check suite — an env file reaches only its agent; README section per
provider.

## Even later

### [ ] 25. Network allowlist and logging (opt-in)

A small egress proxy per pod: deny by default with a per-project domain list, and a log
of allowed destinations. Breaks free web search unless domains are allowed.

### [ ] 26. Nested containers (experiment, gVisor only)

A layer with podman/buildah/fuse-overlayfs; capabilities only for that project's runsc
containers (inside gVisor they apply to the user-space kernel, not the host); image storage
per project. Never with `crun`.
