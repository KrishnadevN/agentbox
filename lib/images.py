#!/usr/bin/env python3
"""agentbox image layers.

  images.py names                 all profile names (package + yours)
  images.py plan [name...]        build plan, one layer per line, parents first:
                                  name<TAB>parent-image<TAB>dir[:dir...]
                                  (no names = all; named layers pull in parents
                                  whose image does not exist yet)

Layers: <package>/images/profiles.toml, then ~/.config/agentbox/images/profiles.toml.
Folders: <package>/images/<name>/ then ~/.config/agentbox/images/<name>/ (adds to it).
"""
import os, subprocess, sys, tomllib

HOME = os.path.expanduser("~")
ROOT = os.environ.get("AB_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.environ.get("AB_CONFIG", os.path.join(os.environ.get("XDG_CONFIG_HOME", f"{HOME}/.config"), "agentbox"))
DIRS = [f"{ROOT}/images", f"{CONFIG}/images"]


def die(msg):
    print(f"agentbox: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def profiles():
    prof = {}
    for d in DIRS:
        try:
            with open(f"{d}/profiles.toml", "rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError:
            continue
        except tomllib.TOMLDecodeError as e:
            die(f"{d}/profiles.toml: {e}")
        for name, v in data.items():
            prof.setdefault(name, {}).update(v)
    for name, v in prof.items():
        if not name.replace("-", "").replace("_", "").isalnum():
            die(f"bad profile name {name!r}")
        if ("from" in v) == ("parent" in v):
            die(f"profile {name!r}: set exactly one of 'from' (external image) or 'parent' (profile)")
        if "parent" in v and v["parent"] not in prof:
            die(f"profile {name!r}: unknown parent {v['parent']!r}")
    return prof


def image(name):
    return f"localhost/sbx-{name}:latest"


def chain(prof, name, seen=()):
    if name in seen:
        die(f"profile loop: {' -> '.join(seen + (name,))}")
    p = prof[name].get("parent")
    return (chain(prof, p, seen + (name,)) if p else []) + [name]


def exists(name):
    return subprocess.run(["podman", "image", "exists", image(name)]).returncode == 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "names"
    prof = profiles()
    if cmd == "names":
        print("\n".join(prof))
        return
    if cmd != "plan":
        die(f"unknown command {cmd!r}")
    want = sys.argv[2:] or list(prof)
    for w in want:
        if w not in prof:
            die(f"unknown profile {w!r}; known: {', '.join(prof)}")
    order = []
    for w in want:
        for n in chain(prof, w):
            explicit = n in want or not sys.argv[2:]
            if n not in order and (explicit or not exists(n)):
                order.append(n)
    for n in order:
        v = prof[n]
        parent = v["from"] if "from" in v else image(v["parent"])
        dirs = [f"{d}/{n}" for d in DIRS if os.path.isdir(f"{d}/{n}")]
        print(f"{n}\t{parent}\t{':'.join(dirs)}")


if __name__ == "__main__":
    main()
