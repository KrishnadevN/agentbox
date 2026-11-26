#!/usr/bin/env python3
"""agentbox rename <old> <new>: move a project's agentbox state to a new name.

Rename the repository folder in $AB_PROJECTS first, with the pod removed. Every check
runs before anything moves. Each move is one rename(2) of the top entry that never
copies and never replaces an existing path (renameat2 with RENAME_NOREPLACE), so no
host operation reaches inside agent-writable folders (AGENTS.md, invariant 3).
"""
import ctypes, os, shlex, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projects as _projects  # noqa: E402

HOME = os.path.expanduser("~")
STATE = os.environ.get("AB_STATE", f"{HOME}/.local/share/agentbox")
CONTEXT = os.environ.get("AB_CONTEXT", f"{HOME}/.agents-context")
CONFIG, AGENTS = _projects.CONFIG, _projects.AGENTS

_libc = ctypes.CDLL(None, use_errno=True)


def die(msg):
    print(f"agentbox: ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def entries(name):
    return [f"{AGENTS}/{name}", f"{STATE}/bridge/{name}.git", f"{STATE}/home/{name}",
            f"{STATE}/ctx/{name}", f"{CONTEXT}/projects/{name}",
            f"{CONTEXT}/project-instructions/{name}.md", f"{CONFIG}/projects/{name}.toml"]


def exists(path):
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False


def move(src, dst):
    """Rename src to dst; fails if dst exists or is on another file system."""
    if _libc.renameat2(-100, os.fsencode(src), -100, os.fsencode(dst), 1) != 0:  # AT_FDCWD, RENAME_NOREPLACE
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e), dst)


def pod_absent(name):
    r = subprocess.run(["podman", "pod", "exists", f"ab-{name}"], capture_output=True)
    if r.returncode == 0:
        die(f"pod ab-{name} exists: run 'agentbox-down {name}' first")
    if r.returncode != 1:
        die(f"could not check pods (podman exit {r.returncode})")


def main(argv):
    if len(argv) != 2:
        print("usage: agentbox rename <old> <new>", file=sys.stderr)
        return 2
    old, new = argv
    if not old or "/" in old or old.startswith("."):
        die(f"bad old name: {old!r}")
    problem = _projects.name_problem(new)
    if problem:
        die(problem)
    if old == new:
        die("old and new name are the same")
    problem = _projects.root_problem()
    if problem:
        die(problem)
    for name in (old, new):
        pod_absent(name)
    found, dups = _projects.discover()
    if old in found or old in dups:
        die(f"{old!r} is still a project in {_projects.ROOT}: rename the folder to {new!r} first")
    if new in dups:
        die(f"project {new!r} exists more than once; rename one of them:\n  " + "\n  ".join(dups[new]))
    if new not in found:
        die(f"no such project: {new} (rename the folder in {_projects.ROOT} first)")
    srcs, dsts = entries(old), entries(new)
    if not exists(srcs[0]):
        die(f"{srcs[0]} does not exist: nothing to rename")
    taken = [d for d in dsts if exists(d)]
    if taken:
        die("already exists, move it away first:\n  " + "\n  ".join(taken))
    repo = found[new].real
    try:      # decide the remote update now: git must work before anything moves
        r = subprocess.run(["git", "-C", repo, "remote"], capture_output=True, text=True)
    except OSError as e:
        die(f"cannot run git: {e.strerror}")
    if r.returncode != 0:
        die(f"git cannot read {repo}: {r.stderr.strip()}")
    has = "agent" in r.stdout.split()
    cmd = ["git", "-C", repo, "remote", "set-url" if has else "add", "agent", dsts[0]]

    done = []
    for s, d in zip(srcs, dsts):
        if not exists(s):
            continue
        try:
            move(s, d)
        except OSError as e:
            left = [f"{a} -> {b}" for a, b in zip(srcs, dsts) if exists(a)]
            die(f"could not move {s} -> {d}: {e.strerror}\n"
                f"moved:\n  " + "\n  ".join(done or ["(nothing)"]) +
                "\nnot moved:\n  " + "\n  ".join(left))
        done.append(f"{s} -> {d}")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        err = r.stderr.strip() if r.returncode else None
    except OSError as e:
        err = e.strerror
    if err is not None:
        die(f"moved everything, but updating the 'agent' remote failed: {err}\n"
            f"run: {shlex.join(cmd)}")
    for line in done:
        print(f"moved {line}")
    print(f"agentbox: renamed {old} -> {new}; start it with: agentbox {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
