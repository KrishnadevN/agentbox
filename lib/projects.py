#!/usr/bin/env python3
"""projects.py: find your projects (git repositories) under $AB_PROJECTS.

Usage: projects.py path <name>              resolved folder of a project (for host git)
       projects.py names                    all project names, one per line
       projects.py list [filter] [--tag T]  tree with config / agent copy / pod state

A project is a folder with its own `.git` DIRECTORY, at most MAX_DEPTH levels below
$AB_PROJECTS. The walk stops at any `.git` (a `.git` file, as in linked worktrees, or a
`.git` symlink is a boundary but not a project: such checkouts share another repo's
remotes and branches), skips hidden folders and does not follow symlinks, so every
folder has exactly one path. Only the $AB_PROJECTS root itself may be a symlink. Nothing
that resolves into agentbox's own or agent-writable trees ($AB_AGENTS, $AB_STATE,
$AB_CONTEXT) is used, a simple guard against mistakes (see AGENTS.md, invariant 8).
The name is the folder's basename; two repos with one name are an error.
"""
import os, stat, subprocess, sys, tomllib
from typing import NamedTuple

HOME = os.path.expanduser("~")
ROOT = os.environ.get("AB_PROJECTS", f"{HOME}/Projects")
CONFIG = os.environ.get("AB_CONFIG", os.path.join(os.environ.get("XDG_CONFIG_HOME", f"{HOME}/.config"), "agentbox"))
AGENTS = os.environ.get("AB_AGENTS", f"{HOME}/.agents-projects")
EXCLUDE = [os.environ.get("AB_AGENTS", f"{HOME}/.agents-projects"),
           os.environ.get("AB_STATE", f"{HOME}/.local/share/agentbox"),
           os.environ.get("AB_CONTEXT", f"{HOME}/.agents-context")]
MAX_DEPTH = 4


class Project(NamedTuple):
    name: str
    path: str      # as discovered under ROOT (for display, category, group)
    real: str      # resolved and checked folder (for host git and file reads)
    category: str  # first folder below ROOT, if depth > 1
    group: str     # parent folder, if depth >= 3
    folders: tuple  # all folders between the (resolved) root and the repo, outer first


def _inside(real, roots):
    return any(real == r or real.startswith(r.rstrip("/") + "/") for r in roots)


def root_problem(root=ROOT, exclude=EXCLUDE):
    """Why the projects root cannot be used, or None."""
    real = os.path.realpath(root)
    if _inside(real, [os.path.realpath(x) for x in exclude]):
        return f"{root} resolves to {real}, inside an agentbox or agent folder: set AB_PROJECTS to your own folder"
    return None


def discover(root=ROOT, exclude=EXCLUDE):
    """-> (projects {name: Project}, duplicates {name: [paths]})"""
    exclude = [os.path.realpath(x) for x in exclude]
    found = []
    if root_problem(root, exclude):
        return {}, {}

    def walk(d, parts):
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError:
            return
        for e in entries:
            try:
                if e.name.startswith(".") or not e.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            real = os.path.realpath(e.path)
            if _inside(real, exclude):
                continue
            p = parts + [e.name]
            g = os.path.join(e.path, ".git")
            try:
                mode = os.lstat(g).st_mode
            except OSError:
                mode = None
            if mode is not None and stat.S_ISDIR(mode):
                found.append(Project(e.name, e.path, real, p[0] if len(p) > 1 else "",
                                     p[-2] if len(p) >= 3 else "", tuple(p[:-1])))
            elif mode is not None and (stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
                continue  # a checkout that shares another repo's git data: boundary only
            elif len(p) < MAX_DEPTH:
                walk(e.path, p)

    walk(os.path.realpath(root), [])
    by_name = {}
    for pr in found:
        by_name.setdefault(pr.name, []).append(pr)
    projects = {n: prs[0] for n, prs in by_name.items() if len(prs) == 1}
    dups = {n: [pr.path for pr in prs] for n, prs in by_name.items() if len(prs) > 1}
    return projects, dups


def lookup(name, found=None, root=ROOT):
    """-> (Project or None, error message or None); found = a discover() result to reuse"""
    problem = root_problem(root)
    if problem:
        return None, problem
    projects, dups = found or discover(root)
    if name in dups:
        return None, (f"project {name!r} exists more than once; rename one of them:\n  "
                      + "\n  ".join(dups[name]))
    if name not in projects:
        return None, f"no such project: {name} (looked in {root}, up to {MAX_DEPTH} levels deep)"
    return projects[name], None


def _tags(name):
    f = f"{CONFIG}/projects/{name}.toml"
    try:
        with open(f, "rb") as fh:
            tags = tomllib.load(fh).get("project", {}).get("tags", [])
    except (OSError, tomllib.TOMLDecodeError):
        return []
    if not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
        print(f"agentbox: WARN: {f}: tags must be a list of strings; ignored", file=sys.stderr)
        return []
    return tags


def _pods():
    try:
        out = subprocess.run(["podman", "pod", "ps", "--format", "{{.Name}}\t{{.Status}}"],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(line.split("\t", 1) for line in out.splitlines() if "\t" in line)


def show_list(args):
    tag, filt = None, None
    while args:
        a = args.pop(0)
        if a == "--tag" and args:
            tag = args.pop(0)
        elif filt is None and not a.startswith("-"):
            filt = a
        else:
            sys.exit("usage: agentbox list [category|group] [--tag TAG]")
    problem = root_problem()
    if problem:
        sys.exit(f"agentbox: ERROR: {problem}")
    projects, dups = discover()
    sel = [p for p in projects.values()
           if (filt is None or filt in (p.category, p.group))
           and (tag is None or tag in _tags(p.name))]
    pods = _pods()
    rows, last = [], ("", "")
    for p in sorted(sel, key=lambda p: (p.category != "", p.category, p.group, p.name)):
        if p.category and p.category != last[0]:
            rows.append((p.category + "/", None))
            last = (p.category, "")
        if p.group and (p.category, p.group) != last:
            rows.append(("  " + p.group + "/", None))
            last = (p.category, p.group)
        indent = "  " * ((1 if p.category else 0) + (1 if p.group else 0))
        rows.append((indent + p.name, p))
    w = max([len(r[0]) for r in rows] + [28]) + 2
    print(f"{'PROJECT':<{w}}{'CONFIG':<8}{'COPY':<6}POD")
    for label, p in rows:
        if p is None:
            print(label)
            continue
        c = "yes" if os.path.isfile(f"{CONFIG}/projects/{p.name}.toml") else "-"
        k = "yes" if os.path.isdir(f"{AGENTS}/{p.name}") else "-"
        print(f"{label:<{w}}{c:<8}{k:<6}{pods.get('ab-' + p.name, '-')}")
    for name, paths in sorted(dups.items()):
        print(f"agentbox: WARN: {name!r} exists more than once (not usable until renamed): "
              + ", ".join(paths), file=sys.stderr)


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "path" and len(argv) == 2:
        p, err = lookup(argv[1])
        if err:
            print(f"agentbox: ERROR: {err}", file=sys.stderr)
            return 1
        print(p.real)
    elif cmd == "names" and len(argv) == 1:
        projects, dups = discover()
        print("\n".join(sorted(set(projects) | set(dups))))
    elif cmd == "list":
        show_list(argv[1:])
    else:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
