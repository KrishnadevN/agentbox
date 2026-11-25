#!/usr/bin/env python3
"""safe_mkdir.py [--file] BASE REL [REL...]

Create BASE/REL directories without following symlinks in any component of REL.
Used for folders that agents can write to (their home, /work, login folders):
an agent could replace a folder with a symlink to a host path, and a plain
`mkdir -p` on the host would then create folders wherever that symlink points.
With --file, REL is a file: its folders are created as above, then the file is
created empty if missing (never truncated, never through a symlink) and must be
a regular file.
Exit 1 (and name the path) if a component is a symlink or not a directory.
"""
import os, stat, sys


def walk(base, rel):
    """Open BASE/REL as a directory fd, creating missing folders, never following symlinks."""
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in [p for p in rel.split("/") if p not in ("", ".")]:
            if part == "..":
                raise ValueError(f"'..' not allowed in {rel!r}")
            try:
                os.mkdir(part, 0o755, dir_fd=fd)
            except FileExistsError:
                pass
            try:
                nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError:
                raise ValueError(f"{os.path.join(base, rel)}: '{part}' is a symlink or not a folder")
            os.close(fd)
            fd = nfd
    except BaseException:
        os.close(fd)
        raise
    return fd


def safe_mkdir(base, rel):
    os.close(walk(base, rel))


def safe_touch(base, rel):
    head, _, name = rel.rstrip("/").rpartition("/")
    if name in ("", ".", ".."):
        raise ValueError(f"not a file name: {rel!r}")
    fd = walk(base, head)
    try:
        try:
            f = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
                        | os.O_CLOEXEC, 0o600, dir_fd=fd)
        except OSError:
            raise ValueError(f"{os.path.join(base, rel)}: is a symlink or not a file")
        try:
            if not stat.S_ISREG(os.fstat(f).st_mode):
                raise ValueError(f"{os.path.join(base, rel)}: not a regular file")
        finally:
            os.close(f)
    finally:
        os.close(fd)


if __name__ == "__main__":
    args = sys.argv[1:]
    fn, what = safe_mkdir, "folder"
    if args[:1] == ["--file"]:
        fn, what, args = safe_touch, "file", args[1:]
    base, rels = args[0], args[1:]
    try:
        for r in rels:
            fn(base, r)
    except (ValueError, OSError) as e:
        print(f"agentbox: ERROR: refusing to create {what}: {e}", file=sys.stderr)
        sys.exit(1)
