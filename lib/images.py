#!/usr/bin/env python3
"""agentbox image layers.

  images.py names                 all profile names (package + yours)
  images.py plan [name...]        build plan, one layer per line, parents first:
                                  name<TAB>parent-image<TAB>dir[:dir...]
                                  (no names = all; named layers pull in parents
                                  whose image does not exist yet)

Layers: <package>/images/profiles.toml, then ~/.config/agentbox/images/profiles.toml.
Folders: <package>/images/<name>/ then ~/.config/agentbox/images/<name>/ (adds to it).
A layer may `include` other layers: their own parts (not their parents) are applied in
dependency order before the layer's own parts. A part is never applied twice in one
image: overlap with what the parent image already supplies is an error.
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
        inc = v.get("include", [])
        if not (isinstance(inc, list) and all(isinstance(i, str) for i in inc)):
            die(f"profile {name!r}: include must be a list of profile names")
        for i in inc:
            if i not in prof:
                die(f"profile {name!r}: unknown include {i!r}")
    return prof


def image(name):
    return f"localhost/sbx-{name}:latest"


def chain(prof, name, seen=()):
    if name in seen:
        die(f"profile loop: {' -> '.join(seen + (name,))}")
    p = prof[name].get("parent")
    return (chain(prof, p, seen + (name,)) if p else []) + [name]


def applied(prof, name, seen=()):
    """Layers whose own parts one build step of `name` applies, in order: the include
    closure in dependency order (an included layer's includes first, each layer once,
    never their parents), then `name` itself."""
    if name in seen:
        die(f"include loop: {' -> '.join(seen + (name,))}")
    out = []
    for i in prof[name].get("include", []):
        for x in applied(prof, i, seen + (name,)):
            if x not in out:
                out.append(x)
    return out + [name]


def supplied(prof, name):
    """All layers whose parts are in the image of `name` (parents, their includes, ...)."""
    base = []
    for n in chain(prof, name):           # parents first; chain() reports parent loops
        mine = applied(prof, n)
        twice = [x for x in mine if x in base]
        if twice:
            die(f"profile {n!r}: {', '.join(twice)} already in the parent image "
                f"{prof[n]['parent']!r}; remove it from include")
        base += mine
    return base


def uses(prof, name, layer):
    """True if the image of `name` contains `layer`'s parts (as parent or include)."""
    return layer in supplied(prof, name)


def layer_dirs(prof, name):
    """Folders one build step of `name` applies, in order."""
    supplied(prof, name)  # validates: no part twice in the image
    return [f"{d}/{n}" for n in applied(prof, name) for d in DIRS if os.path.isdir(f"{d}/{n}")]


def plan(prof, want, exists, named):
    """[(name, parent image, folders)] parents first. named: the user listed `want`
    (layers missing from the plan are built only if their image does not exist)."""
    order = []
    for w in want:
        for n in chain(prof, w):
            if n not in order and (n in want or not named or not exists(n)):
                order.append(n)
    out = []
    for n in order:
        v = prof[n]
        out.append((n, v["from"] if "from" in v else image(v["parent"]), layer_dirs(prof, n)))
    return out


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
    for n, parent, dirs in plan(prof, want, exists, bool(sys.argv[2:])):
        print(f"{n}\t{parent}\t{':'.join(dirs)}")


if __name__ == "__main__":
    main()
