#!/usr/bin/env python3
"""safe_mkdir.py BASE REL [REL...]

Create BASE/REL directories without following symlinks in any component of REL.
Used for folders that agents can write to (their home, /work, login folders):
an agent could replace a folder with a symlink to a host path, and a plain
`mkdir -p` on the host would then create folders wherever that symlink points.
Exit 1 (and name the path) if a component is a symlink or not a directory.
"""
import os, sys

def safe_mkdir(base, rel):
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
    finally:
        os.close(fd)

if __name__ == "__main__":
    base, rels = sys.argv[1], sys.argv[2:]
    try:
        for r in rels:
            safe_mkdir(base, r)
    except (ValueError, OSError) as e:
        print(f"agentbox: ERROR: refusing to create folder: {e}", file=sys.stderr)
        sys.exit(1)
