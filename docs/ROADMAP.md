# Roadmap

Ordered by priority. One item = one commit (or a short series if the item says so).
Each milestone becomes a minor release; publish `-beta.N` tags while testing.
Read `AGENTS.md` first. "Verify" marks facts that must be checked against the current
tool version before relying on them.

Status: `[ ]` open · `[~]` in progress · `[x]` done

---

## 0.2.0 — Nested projects and composable images (high)

### [ ] 1. Per-project agent sessions (privacy fix)

Problem: each agent's config folder (`auth/<agent>`) is shared by all projects, and the
working directory is `/work` everywhere. So conversation history from every project lands
in the same place: Claude Code under `projects/-work/` (plus `history.jsonl`, todos, file
history), Codex under `sessions/` and `history.jsonl`, Copilot and Antigravity similarly.
Effects: `/resume` lists sessions of all projects mixed, `--continue` can pick up another
project's conversation, and an agent in project A can read project B's transcripts.

Design:
- Keep the login shared; make session data per project. New per-agent config
  `sessions = [...]`: paths inside the agent's config folder that are bind-mounted from
  `~/.local/share/agentbox/sessions/<project>/<agent>/...` over the shared folder.
  Defaults to verify against current versions (folders and files):
  Claude `projects/`, `history.jsonl`, `todos/`, `file-history/`, `shell-snapshots/`,
  `plans/`; Codex `sessions/`, `archived_sessions/`, `history.jsonl`; Copilot
  `session-state/`, `history-session-state/`; Antigravity: find its session folder.
- Create mount points with `ab_safe_mkdir`; create file targets only if missing and not
  symlinks (same rule as the instruction files).
- One-time migration is not needed (old mixed history stays in the shared folder); say so
  in the CHANGELOG and suggest deleting it.
- Afterwards `/resume` and `--continue` (item 8) only see the current project's sessions.

Acceptance: check suite — a file written to the session folder in project A is not visible
in project B's container; the login file is still shared.

### [ ] 2. Nested project discovery

Goal: projects may live at any depth (≤ 4) under `~/Projects`, e.g.
`research/ProjectName/ProjectName-manuscript`. Nothing is stored separately, so nothing
goes out of sync.

Design (decided):
- A project is a folder that contains `.git` (folder **or** file). Walk `$AB_PROJECTS` to
  depth 4 and **stop descending** once a folder contains `.git`; nested repos are ignored.
  Skip hidden folders. Implement in Python (`lib/projects.py`, stdlib only).
- Project name = the repo folder's own name (basename). It stays the key everywhere:
  `~/.agents-projects/<name>` (flat), `~/.config/agentbox/projects/<name>.toml`, pod
  `ab-<name>`, `~/.agents-context/projects/<name>/`.
- Two repos with the same name → refuse to start, list both paths.
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
  as file, nested repo ignored, duplicate detection, category/group derivation.
- Existing flat projects keep working unchanged.
- Check suite passes; CI runs the unit tests.

### [ ] 3. Group configuration and group instructions

- Merge order becomes: package defaults < `config.toml` < `hosts/<host>.toml` <
  `groups/<category>.toml` < `groups/<group>.toml` < `projects/<name>.toml` < hint < CLI.
- Group instructions: append `~/.agents-context/groups/<category>.md` and
  `~/.agents-context/groups/<group>.md` (if present) to each agent's context file, after
  `instructions/all.md` and `instructions/<agent>.md`.
- Same rule as for projects: the global cap (`[resources] reserve_*`) is ignored in group
  files, with a warning.

Acceptance: example files in `examples/groups/`; README section; a cfg.py test for the
merge order.

### [ ] 4. Per-project environment and project references

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

### [ ] 5. Layer `include`

- `images/profiles.toml` (and the user's) may set `include = ["docs", ...]` on a layer.
  The build copies the included layers' own parts (packages, files, setup, env — not their
  parents) into this layer, in order, before the layer's own parts. Detect cycles.
- Example in `examples/`: `[webdocs] parent = "web"`, `include = ["docs"]`.
- Document the trade-off: included parts are stored again in this image.

Acceptance: `images.py plan` test with include + cycle; build of the example succeeds.

### [ ] 6. `agentbox rename <old> <new>`

For renames like a placeholder → `JournalName2027`. The user renames the repo folder first;
then this command moves `~/.agents-projects/<old>`, the bridge, `ctx/`, `home/`,
`~/.agents-context/projects/<old>`, `projects/<old>.toml`, the slice file, and updates the
trusted repo's `agent` remote. Refuses while the pod runs. Host-side moves of
agent-writable folders: rename the top folder only (no traversal inside).

### [ ] 7. Release 0.2.0

README (layout, groups, env, include, rename), CHANGELOG, examples; beta tag, test on the
laptop, then `v0.2.0`.

---

## 0.3.0 — Agent workflow (medium)

### [ ] 8. Pass arguments to the agent

`agentbox <p> claude -- --continue` → everything after `--` is appended to the agent
command. Same for `codex`, `agy`, `copilot`.

### [ ] 9. Handoff folder and review-workflow instructions

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

### [ ] 10. Headless runs: `agentbox <p> run <agent> [--resume] "<prompt>"`

- New config per agent: `headless` and `headless_resume` command lists.
  Defaults to verify: Claude `claude -p --dangerously-skip-permissions` (+ `--continue`);
  Codex `codex exec --dangerously-bypass-approvals-and-sandbox` (resume: `codex exec resume
  --last`). Agy and Copilot: verify their headless flags; leave empty if unknown.
- Runs in the agent's own container (`podman exec` without TTY), output also appended to
  `/work/.agentbox/handoff/run-<agent>.log`.

### [ ] 11. `agentbox <p> review [branch]`

Fetch, then in the trusted repo: commit list and `diff --stat` of `agent/<branch>` against
the default branch (detect `main`/`master`). Read-only; merging stays manual.

### [ ] 12. Notifications

Defaults written by prep into the sandbox login folders (only if not set): Claude terminal
bell, Codex terminal notifications (verify setting names). README: kitty shows them; in
tmux set `monitor-bell on` and `allow-passthrough on`. No D-Bus, no host sockets.

### [ ] 13. `agentbox doctor` and `agentbox clean <p>`

- `doctor`: versions (agentbox, podman, runsc, CLIs), paths agentbox writes outside the
  package with sizes, stale slices/pods/state for projects that no longer exist, Podman
  storage use.
- `clean <p>`: with the pod down, remove that project's agent copy, bridge, `ctx/`,
  `home/`, slice file (asks first; never touches `~/Projects`, never touches
  `~/.agents-context` without `--context`).

### [ ] 14. Image name prefix for development

`AB_IMAGE_PREFIX` (default `sbx`) used by `images.py`, `cfg.py`, `agentbox-update-tools`, so
a development checkout can build and test `localhost/sbxdev-*` without replacing the images
real projects use.

### [ ] 15. Release 0.3.0

---

## 0.4.0 — Workstation and tmux (low)

### [ ] 16. Fedora Atomic (Kinoite/Silverblue) support in prep

- Detect rpm-ostree; Podman is preinstalled; install missing pieces by layering only if
  needed; gVisor tarball into `/usr/local/bin` (writable on ostree).
- SELinux: shared mounts need `:z`; private ones `:Z`; never relabel `$HOME` itself.
  Verify how runsc handles labels; `setsebool -P container_use_devices=true` for GPU.
- Check suite must pass on Kinoite.

### [ ] 17. NVIDIA GPU tier

Host `gpu = "nvidia-cdi"`; project `gpu = "optional" | "required"`. With a GPU: `crun` +
`--device nvidia.com/gpu=all` for the containers that need it (runsc + nvproxy stays an
experiment). Optional `cuda` layer for `nvcc`. Check: `nvidia-smi` and
`torch.cuda.is_available()` in the container; CPU fallback on hosts without GPU.

### [ ] 18. tmux layout

`agentbox <p>` (no action) opens or re-attaches tmux session `ab-<p>`: window `host`
(trusted repo folder, plain host shell), one window per agent, `dev`. `monitor-activity`
on agent windows. Scripts never `send-keys` agent-written content.

### [ ] 19. Release 0.4.0

---

## Later (lower)

### [ ] 20. `agentbox <p> loop` — automated implement/review rounds

Host-side, after the protocol of item 9 has worked manually for a while. Reads `STATUS.md`
strictly (allowed values only, size cap), sends only fixed prompts via `run --resume`,
stops at `approved-by-agents`, `needs-human` or the round limit.

### [ ] 21. Per-agent worktrees (opt-in)

`worktrees = true`: each agent container gets its own git worktree/branch of the agent
copy, created inside the sandbox so paths match. Only if parallel agents become common.

---

## Even later

### [ ] 22. Network allowlist and logging (opt-in)

A small egress proxy per pod: deny by default with a per-project domain list, and a log
of allowed destinations. Breaks free web search unless domains are allowed.

### [ ] 23. Nested containers (experiment, gVisor only)

A layer with podman/buildah/fuse-overlayfs; capabilities only for that project's runsc
containers (inside gVisor they apply to the user-space kernel, not the host); image storage
per project. Never with `crun`.
