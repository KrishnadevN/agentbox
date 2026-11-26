"""Folder (group) config, instruction modules and the instruction part of the config hash.
Run: python3 -m unittest discover -s tests"""
import os, shlex, socket, subprocess, sys, tempfile, unittest

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
CFG = os.path.join(LIB, "cfg.py")
HOST = socket.gethostname().split(".")[0]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class GroupConfigTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self.t = os.path.realpath(self._tmp.name)
        self.cfg, self.ctx = f"{t}/cfg", f"{t}/ctx"
        for d in ("a/b/c/proj", "flat", "research/code/r1", "teaching/code/t1"):
            os.makedirs(f"{t}/real-projects/{d}/.git")
        os.symlink(f"{t}/real-projects", f"{t}/Projects")   # AB_PROJECTS is a symlink
        os.makedirs(f"{t}/home")
        write(f"{self.cfg}/hosts/{HOST}.toml", "")
        self.env = dict(os.environ, HOME=f"{t}/home", AB_CONFIG=self.cfg, AB_PROJECTS=f"{t}/Projects",
                        AB_AGENTS=f"{t}/agents", AB_STATE=f"{t}/state", AB_CONTEXT=self.ctx)
        self.env.pop("AB_CFG_QUIET", None)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cfg(self, project, *args):
        return subprocess.run(["python3", CFG, project, *args], capture_output=True, text=True, env=self.env)

    def ok(self, project, *args):
        r = self.run_cfg(project, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def out(self, r, key):
        line = next(l for l in r.stdout.splitlines() if l.startswith(key + "="))
        return shlex.split(line.split("=", 1)[1].strip("()"))

    def py(self, code):
        """Run code with lib/ importable and this test's environment (module constants)."""
        r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {LIB!r})\n" + code],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_folders_and_layers_through_symlinked_root(self):
        got = self.py("import cfg, projects\n"
                      "p, err = projects.lookup('proj')\n"
                      "print(p.folders)\n"
                      "for f in cfg.layers(p, 'h'): print(f)")
        lines = got.splitlines()
        self.assertEqual(lines[0], "('a', 'b', 'c')")
        c = self.cfg
        self.assertEqual(lines[2:], [f"{c}/config.toml", f"{c}/hosts/h.toml", f"{c}/groups/a/group.toml",
                                     f"{c}/groups/a/b/group.toml", f"{c}/groups/a/b/c/group.toml",
                                     f"{c}/projects/proj.toml"])
        self.assertTrue(lines[1].endswith("/defaults.toml"))

    def test_every_layer_visible_in_merge_chain(self):
        # Layer i sets keys i..end; each later layer overrides only the keys after it.
        keys = ["profile", "mem", "cpus", "dev_runtime", "agents"]
        vals = [("profile", '"docs"'), ("mem", '"5G"'), ("cpus", "3"),
                ("dev_runtime", '"crun"'), ("agents", '["codex"]')]
        paths = [f"{self.cfg}/hosts/{HOST}.toml", f"{self.cfg}/groups/a/group.toml",
                 f"{self.cfg}/groups/a/b/group.toml", f"{self.cfg}/groups/a/b/c/group.toml",
                 f"{self.cfg}/projects/proj.toml"]
        junk = {"profile": '"web"', "mem": '"9G"', "cpus": "9", "dev_runtime": '"runsc"', "agents": '["agy"]'}
        for i, path in enumerate(paths):
            lines = [f"{vals[i][0]} = {vals[i][1]}"] + [f"{k} = {junk[k]}" for k in keys[i + 1:]]
            write(path, "[project]\n" + "\n".join(lines) + "\n")
        r = self.ok("proj")
        self.assertEqual(self.out(r, "PROFILE"), ["docs"])     # host
        self.assertEqual(self.out(r, "PMEM"), ["5G"])           # a
        self.assertEqual(self.out(r, "PCPUS"), ["3"])           # a/b
        self.assertEqual(self.out(r, "DEVRT"), ["crun"])        # a/b/c
        self.assertEqual(self.out(r, "AGENTS"), ["codex"])      # project
        r = self.ok("proj", "--cpus", "2")                      # CLI on top
        self.assertEqual(self.out(r, "PCPUS"), ["2"])
        self.assertEqual(self.out(r, "PMEM"), ["5G"])

    def test_flat_project_and_same_named_groups(self):
        write(f"{self.cfg}/groups/research/code/group.toml", '[project]\nmem = "6G"\n')
        write(f"{self.cfg}/groups/teaching/code/group.toml", '[project]\nmem = "7G"\n')
        self.assertEqual(self.out(self.ok("r1"), "PMEM"), ["6G"])
        self.assertEqual(self.out(self.ok("t1"), "PMEM"), ["7G"])
        self.assertEqual(self.out(self.ok("flat"), "PMEM"), [""])

    def test_folder_named_group_toml_does_not_break_start(self):
        os.makedirs(f"{self.t}/real-projects/x/group.toml/y/.git")
        os.makedirs(f"{self.t}/real-projects/x/group.toml/z/proj2/.git")
        os.makedirs(f"{self.cfg}/groups/x/group.toml/y")          # dir where x's file would be
        self.ok("y")
        os.rmdir(f"{self.cfg}/groups/x/group.toml/y")
        os.rmdir(f"{self.cfg}/groups/x/group.toml")
        write(f"{self.cfg}/groups/x/group.toml", '[project]\nmem = "6G"\n')   # file blocks the child path
        self.assertEqual(self.out(self.ok("proj2"), "PMEM"), ["6G"])

    def test_fifo_instruction_file_is_skipped(self):
        os.makedirs(f"{self.ctx}/groups/a")
        os.mkfifo(f"{self.ctx}/groups/a/group.md")
        os.makedirs(f"{self.ctx}/instructions")
        os.mkfifo(f"{self.ctx}/instructions/all.md")
        r = subprocess.run(["python3", CFG, "proj"], capture_output=True, text=True, env=self.env, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.out(r, "CTX_EXTRA"), [])

    def test_global_cap_in_group_file_warns_and_is_ignored(self):
        before = self.out(self.ok("proj"), "CPUS")
        write(f"{self.cfg}/groups/a/group.toml", "[resources]\nreserve_threads = 999\n")
        r = self.ok("proj")
        self.assertIn("groups/a/group.toml: [resources] reserve_threads ignored", r.stderr)
        self.assertEqual(self.out(r, "CPUS"), before)

    def test_ctx_extra_order_and_missing_module(self):
        write(f"{self.cfg}/groups/a/b/group.toml", '[context]\ninstructions = ["latex", "gone", "py"]\n')
        names = ["instructions/latex.md", "instructions/py.md", "groups/a/group.md",
                 "groups/a/b/c/group.md", "project-instructions/proj.md"]
        for n in names:
            write(f"{self.ctx}/{n}", n)
        r = self.ok("proj")
        self.assertEqual(self.out(r, "CTX_EXTRA"), [f"{self.ctx}/{n}" for n in names])
        self.assertIn("instructions/gone.md missing: skipped", r.stderr)

    def test_bad_module_names_rejected(self):
        for bad in ('"../x"', '"a/b"', '".x"', '""', '"all"', '"dev"', '"claude"'):
            write(f"{self.cfg}/projects/proj.toml", f"[context]\ninstructions = [{bad}]\n")
            r = self.run_cfg("proj")
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("bad module name", r.stderr)

    def test_hint_cannot_select_modules(self):
        write(f"{self.ctx}/instructions/secret.md", "x")
        write(f"{self.t}/real-projects/flat/.agentbox-hint.toml", '[context]\ninstructions = ["secret"]\n')
        r = self.ok("flat")
        self.assertIn("ignored (hints may only lower privileges)", r.stderr)
        self.assertEqual(self.out(r, "CTX_EXTRA"), [])

    def test_hash_follows_instruction_contents(self):
        def h():
            return self.out(self.ok("proj"), "CFGHASH")[0]
        f = f"{self.ctx}/groups/a/group.md"
        h0 = h()
        write(f, "one")
        h1 = h()
        write(f, "two")                       # same path, new content
        h2 = h()
        write(f"{self.ctx}/instructions/dev.md", "dev")
        h3 = h()
        self.assertEqual(len({h0, h1, h2, h3}), 4)


if __name__ == "__main__":
    unittest.main()
