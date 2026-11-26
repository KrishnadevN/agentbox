#!/usr/bin/env python3
"""agentbox config merger.

Usage: cfg.py <project> [--runtime runsc|crun] [--mem 32G] [--cpus N]
              [--ro PATH]... [--offline]

Order (later wins): package defaults.toml -> $AB_CONFIG/config.toml ->
$AB_CONFIG/hosts/<hostname>.toml -> $AB_CONFIG/projects/<project>.toml ->
hint file in the project's repo (may only LOWER privileges) -> CLI options.
$AB_CONFIG defaults to ~/.config/agentbox (your config, separate from the package).

Prints bash assignments on stdout (for `eval`). Warnings go to stderr.
The project repo itself is never trusted for mounts, ports or runtime.
"""
import argparse, hashlib, json, os, shlex, socket, sys, tomllib

HOME = os.path.expanduser("~")
ROOT = os.environ.get("AB_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG = os.environ.get("AB_CONFIG", os.path.join(os.environ.get("XDG_CONFIG_HOME", f"{HOME}/.config"), "agentbox"))
STATE = os.environ.get("AB_STATE", f"{HOME}/.local/share/agentbox")
PROJECTS = os.environ.get("AB_PROJECTS", f"{HOME}/Projects")
AGENTS_DIR = os.environ.get("AB_AGENTS", f"{HOME}/.agents-projects")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import images as _images  # noqa: E402  (layer definitions: images/profiles.toml + yours)
import projects as _projects  # noqa: E402  (project discovery under $AB_PROJECTS)


def parse_ident(s, what):
    """'Name <email>' -> (name, email)"""
    s = str(s).strip()
    if not (s.endswith(">") and "<" in s):
        die(f"{what}: expected 'Name <email>', got {s!r}")
    name, email = s[:-1].split("<", 1)
    return name.strip(), email.strip()
KNOWN_AGENTS = ("claude", "codex", "agy", "copilot")
RUNTIMES = ("runsc", "crun")

# Never mount these, their parents, or anything inside them.
PROTECTED = [f"{HOME}/{p}" for p in (
    ".ssh", ".gnupg", ".config", ".password-store", ".mozilla", ".pki",
    ".local/share/keyrings", ".netrc", ".git-credentials", ".docker",
)] + [STATE, ROOT, CONFIG, AGENTS_DIR]


def warn(msg):
    if os.environ.get("AB_CFG_QUIET"):
        return
    print(f"agentbox: WARN: {msg}", file=sys.stderr)


def die(msg):
    print(f"agentbox: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return None
    except tomllib.TOMLDecodeError as e:
        die(f"{path}: {e}")


def merge(a, b):
    for k, v in (b or {}).items():
        a[k] = merge(dict(a.get(k, {})), v) if isinstance(v, dict) else v
    return a


def gib(s):
    s = str(s).strip().upper().rstrip("B")
    mult = {"G": 1, "M": 1 / 1024, "T": 1024}.get(s[-1:], None)
    try:
        return float(s[:-1]) * mult if mult else float(s)
    except ValueError:
        die(f"bad size: {s!r} (use e.g. 48G or 512M)")


def check_mount(path):
    real = os.path.realpath(os.path.expanduser(path))
    if not os.path.exists(real):
        die(f"mount source does not exist: {path}")
    def is_ancestor_or_same(anc, x):
        return x == anc or x.startswith(anc.rstrip("/") + "/")
    for p in map(os.path.realpath, PROTECTED):
        if is_ancestor_or_same(real, p) or is_ancestor_or_same(p, real):
            die(f"refusing to mount {real}: overlaps protected path {p}")
    for p in map(os.path.realpath, (HOME, "/")):
        if is_ancestor_or_same(real, p):  # $HOME itself, / , or a parent of $HOME
            die(f"refusing to mount {real}: too broad")
    if is_ancestor_or_same(os.path.realpath(PROJECTS), real):  # every project lives under it
        warn(f"{real} is a working tree: uncommitted files and secrets (.env) there become readable")
    return real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--runtime", choices=RUNTIMES)
    ap.add_argument("--mem")
    ap.add_argument("--cpus", type=int)
    ap.add_argument("--ro", action="append", default=[])
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()

    p = a.project
    if "/" in p or p.startswith(".") or not p:
        die(f"bad project name: {p!r}")

    found = _projects.discover()
    proj, err = _projects.lookup(p, found)
    if err:
        die(err)
    src = proj.real       # resolved and checked by discovery: used for host reads

    host = socket.gethostname().split(".")[0]
    cfg = load(f"{ROOT}/defaults.toml") or die(f"{ROOT}/defaults.toml missing")
    merge(cfg, load(f"{CONFIG}/config.toml"))
    hcfg = load(f"{CONFIG}/hosts/{host}.toml")
    if hcfg is None:
        warn(f"{CONFIG}/hosts/{host}.toml missing: using defaults (run agentbox-prep.sh to create it)")
    merge(cfg, hcfg)
    # The global cap (agents.slice) is shared by ALL projects: compute it from
    # defaults + host only, so one project file cannot change it for the others.
    rs_global = dict(cfg["resources"])
    pcfg = load(f"{CONFIG}/projects/{p}.toml")
    if pcfg is None:
        warn(f"{CONFIG}/projects/{p}.toml missing: using the DEFAULT profile ({cfg['project']['profile']})")
    merge(cfg, pcfg)

    pr, rs, net, rt = cfg["project"], cfg["resources"], cfg["network"], cfg["runtime"]
    hst = cfg.get("host", {})

    # Hint file in YOUR repo: may only lower privileges.
    hint = load(f"{src}/.agentbox-hint.toml") or {}
    for k, v in hint.items():
        if k == "network" and v == "offline":
            net["mode"] = "offline"
        elif k == "runtime" and v == "runsc":
            rt["default"] = "runsc"
        else:
            warn(f".agentbox-hint.toml: '{k} = {v!r}' ignored (hints may only lower privileges)")

    if a.runtime:
        rt["default"] = a.runtime
    if a.offline:
        net["mode"] = "offline"
    if a.mem:
        pr["mem"] = a.mem
    if a.cpus:
        pr["cpus"] = a.cpus

    IMAGES = {n: _images.image(n) for n in _images.profiles()}
    profile = pr["profile"]
    if profile not in IMAGES:
        die(f"unknown profile {profile!r}; use one of {', '.join(IMAGES)}")
    if cfg.get("git"):
        warn("[git] section is no longer used: commits use your host identity; "
             "put commit conventions in AGENTS.md / CLAUDE.md")
    agents = [x for x in pr["agents"] if x in KNOWN_AGENTS]
    for x in set(pr["agents"]) - set(agents):
        warn(f"unknown agent {x!r} ignored")
    runtime = rt["default"]
    dev_rt = pr.get("dev_runtime") or runtime
    for r in (runtime, dev_rt):
        if r not in RUNTIMES:
            die(f"unknown runtime {r!r}")

    # Resources: computed live from this machine.
    with open("/proc/meminfo") as f:
        total = int(next(l for l in f if l.startswith("MemTotal")).split()[1]) / 2**20
    threads = os.cpu_count() or 1
    for k in ("reserve_mem_gib_min", "reserve_mem_pct", "reserve_threads", "memory_high_pct", "tasks_max"):
        if (pcfg or {}).get("resources", {}).get(k) is not None:
            warn(f"projects/{p}.toml: [resources] {k} ignored (global; set it in hosts/{host}.toml). Use [project] mem/cpus")
    g = rs_global
    reserve = max(g["reserve_mem_gib_min"], total * g["reserve_mem_pct"] / 100)
    memmax = max(4, int(total - reserve))
    memhigh = max(2, int(memmax * g["memory_high_pct"] / 100))
    cpus = max(1, threads - g["reserve_threads"])
    pmem = gib(pr["mem"]) if pr.get("mem") else 0
    pcpus = int(pr.get("cpus") or 0)
    if pmem and pmem > memmax:
        warn(f"project mem {pmem:g}G > global cap {memmax}G; global cap still applies")
    jobt = pcpus or cpus
    if rs.get("threads_per_job"):
        jobt = min(jobt, rs["threads_per_job"])

    # Mounts (read-only only; writable extras are deliberately not offered).
    mounts, seen = [], set()
    for kind, paths in (("data", pr.get("data_ro", [])), ("ref", pr.get("ref_ro", []) + a.ro)):
        for path in paths:
            real = check_mount(path)
            base = os.path.basename(real.rstrip("/")) or "root"
            dst, n = f"/{kind}/{base}", 2
            while dst in seen:
                dst, n = f"/{kind}/{base}_{n}", n + 1
            seen.add(dst)
            mounts += ["-v", f"{real}:{dst}:ro"]

    tex = hst.get("tex_root", "")
    if _images.uses(_images.profiles(), profile, "docs"):   # docs as parent or include
        if tex and os.path.isdir(tex):
            tex = os.path.realpath(tex)     # TEX_ROOT must exist at the same path inside
            texsrc = check_mount(os.path.dirname(tex))   # the folder actually mounted
            mounts += ["-v", f"{texsrc}:{texsrc}:ro"]
        else:
            warn(f"profile {profile}: TeX Live not found at tex_root={tex!r}; LaTeX will be missing "
                 f"(run scripts/agentbox-install-texlive.sh, then set tex_root in {CONFIG}/hosts/{host}.toml)")
            tex = ""

    publish = []
    for e in pr.get("publish", []):
        parts = str(e).split(":")
        if len(parts) == 1:
            parts = ["127.0.0.1", parts[0], parts[0]]
        elif len(parts) == 2:
            parts = ["127.0.0.1"] + parts
        if parts[0] != "127.0.0.1":
            warn(f"publish {e!r}: forced to 127.0.0.1 (never expose agents on the LAN)")
            parts[0] = "127.0.0.1"
        publish.append(":".join(parts))

    norm = "".join(c if c.isalnum() or c == "_" else "_" for c in p)
    effective = dict(profile=profile, image=IMAGES[profile], runtime=runtime, dev_rt=dev_rt,
                     agents=agents, dev=bool(pr.get("dev", True)), net=net["mode"],
                     dns=net["dns"], publish=publish, mounts=mounts, tex=tex,
                     flags=rt["runsc_flags"], gpu=hst.get("gpu", "none"),
                     idents={a: cfg.get("agents", {}).get(a, {}).get("git") for a in KNOWN_AGENTS},
                     context=cfg.get("context", {}),
                     skills={a: cfg.get("agents", {}).get(a, {}).get("skills") for a in KNOWN_AGENTS})
    cfghash = hashlib.sha256(json.dumps(effective, sort_keys=True).encode()).hexdigest()[:12]

    out = dict(
        P=p, NORM=norm, POD=f"ab-{p}", SLICE=f"agents-{norm}.slice",
        SRC=src, WORK=f"{AGENTS_DIR}/{p}", BRIDGE=f"{STATE}/bridge/{p}.git",
        PROFILE=profile, IMAGE=IMAGES[profile], RT=runtime, DEVRT=dev_rt,
        NET=net["mode"], DEV=int(effective["dev"]), TEX_ROOT=tex,
        HOST_LABEL=hst.get("label", host), GPU=hst.get("gpu", "none"),
        MEMMAX=f"{memmax}G", MEMHIGH=f"{memhigh}G", CPUS=cpus, TASKS=g["tasks_max"],
        PMEM=f"{int(pmem)}G" if pmem else "", PMEMHIGH=f"{int(pmem * 0.9 * 1024)}M" if pmem else "",
        PCPUS=pcpus or "", JOBT=jobt, CFGHASH=cfghash,
        UPDATE_MAX_AGE_H=cfg.get("tools", {}).get("update_max_age_hours", 12),
    )
    arrays = dict(RTFLAGS=rt["runsc_flags"], DNS=net["dns"], PUBLISH=publish,
                  XMOUNTS=mounts, AGENTS=agents)
    ctx = cfg.get("context", {})
    skills_mode = ctx.get("skills", "ro")
    if skills_mode not in ("ro", "rw", "off"):
        die("[context] skills must be ro, rw or off")
    out["CTX_FILES"] = int(bool(ctx.get("project_files", True)))
    out["SKILLS_MODE"] = skills_mode
    for ag in KNOWN_AGENTS:
        a_cfg = cfg.get("agents", {}).get(ag, {})
        arrays[f"CMD_{ag}"] = a_cfg.get("cmd", [ag])
        sk = a_cfg.get("skills", [])
        for d in sk:
            if not str(d).startswith("/home/agent/") or ".." in str(d):
                die(f"[agents.{ag}] skills: {d!r} must be a path under /home/agent/")
        arrays[f"SKILLS_{ag}"] = sk
        n, e = parse_ident(a_cfg.get("git", f"{ag} (agentbox) <{ag}@agentbox.invalid>"), f"[agents.{ag}] git")
        out[f"GITNAME_{ag}"], out[f"GITEMAIL_{ag}"] = n, e

    for k, v in out.items():
        print(f"{k}={shlex.quote(str(v))}")
    for k, v in arrays.items():
        print(f"{k}=(" + " ".join(shlex.quote(str(x)) for x in v) + ")")


if __name__ == "__main__":
    main()
