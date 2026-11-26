"""[project] env and project:/agents: references in ref_ro, data_ro and --ro.
Run: python3 -m unittest discover -s tests"""
import os, shlex, socket, subprocess, tempfile, unittest

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "cfg.py")
HOST = socket.gethostname().split(".")[0]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class EnvRefsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self.t = os.path.realpath(self._tmp.name)
        self.cfg, self.agents = f"{t}/cfg", f"{t}/agents"
        for d in ("cat/proj", "other", "x/dup", "y/dup"):
            os.makedirs(f"{t}/Projects/{d}/.git")
        os.makedirs(f"{t}/home")
        os.makedirs(f"{self.agents}/other")
        write(f"{self.cfg}/hosts/{HOST}.toml", "")
        self.env = dict(os.environ, HOME=f"{t}/home", AB_CONFIG=self.cfg, AB_PROJECTS=f"{t}/Projects",
                        AB_AGENTS=self.agents, AB_STATE=f"{t}/state", AB_CONTEXT=f"{t}/ctx")
        self.env.pop("AB_CFG_QUIET", None)

    def tearDown(self):
        self._tmp.cleanup()

    def project(self, text):
        write(f"{self.cfg}/projects/proj.toml", text)

    def run_cfg(self, *args):
        return subprocess.run(["python3", CFG, "proj", *args], capture_output=True, text=True, env=self.env)

    def ok(self, *args):
        r = self.run_cfg(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def fails(self, msg, *args):
        r = self.run_cfg(*args)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(msg, r.stderr)
        return r

    def out(self, r, key):
        line = next(l for l in r.stdout.splitlines() if l.startswith(key + "="))
        v = line.split("=", 1)[1]
        return shlex.split(v[1:-1] if v.startswith("(") else v)

    # ---- env
    def test_env_layers_combine_and_project_wins(self):
        write(f"{self.cfg}/groups/cat/group.toml", '[project]\nenv = { A = "group", B = "group" }\n')
        self.project('[project]\nenv = { B = "x y=z", C = "proj" }\n')
        self.assertEqual(self.out(self.ok(), "ENV_ARGS"),
                         ["-e", "A=group", "-e", "B=x y=z", "-e", "C=proj"])

    def test_reserved_env_dropped_with_warning(self):
        self.project('[project]\nenv = { HOME = "/x", PATH = "/x", AGENTBOX_HOST = "x", '
                     'GIT_CONFIG_GLOBAL = "/x", COPILOT_GITHUB_TOKEN = "t", OK = "1" }\n')
        r = self.ok()
        self.assertEqual(self.out(r, "ENV_ARGS"), ["-e", "OK=1"])
        for k in ("HOME", "PATH", "AGENTBOX_HOST", "GIT_CONFIG_GLOBAL", "COPILOT_GITHUB_TOKEN"):
            self.assertIn(f"env: {k} ignored", r.stderr)

    def test_bad_env_rejected(self):
        for text, msg in (('env = { "1A" = "x" }', "bad variable name"),
                          ('env = { "A-B" = "x" }', "bad variable name"),
                          ("env = { A = 1 }", "must be a string"),
                          ('env = { A = "x\\u0000y" }', "without NUL"),
                          ('env = "A=1"', "must be a table")):
            self.project(f"[project]\n{text}\n")
            self.fails(msg)

    def test_malformed_env_in_early_layer_reported_before_merge(self):
        write(f"{self.cfg}/config.toml", '[project]\nenv = "A=1"\n')
        self.project('[project]\nenv = { A = "1" }\n')
        self.fails(f"{self.cfg}/config.toml: [project] env must be a table")

    def test_hint_cannot_set_env(self):
        write(f"{self.t}/Projects/cat/proj/.agentbox-hint.toml", '[project]\nenv = { A = "1" }\n')
        r = self.ok()
        self.assertEqual(self.out(r, "ENV_ARGS"), [])
        self.assertIn("ignored (hints may only lower privileges)", r.stderr)

    def test_env_change_changes_hash(self):
        self.project('[project]\nenv = { A = "1" }\n')
        h1 = self.out(self.ok(), "CFGHASH")
        self.project('[project]\nenv = { A = "2" }\n')
        self.assertNotEqual(h1, self.out(self.ok(), "CFGHASH"))

    # ---- project: and agents:
    def test_project_and_agents_refs(self):
        self.project('[project]\nref_ro = ["agents:other", "project:other"]\ndata_ro = ["project:other"]\n')
        m = self.out(self.ok(), "XMOUNTS")
        self.assertEqual(m, ["-v", f"{self.t}/Projects/other:/data/other:ro",
                             "-v", f"{self.agents}/other:/ref/other:ro",
                             "-v", f"{self.t}/Projects/other:/ref/other_2:ro"])

    def test_project_ref_from_cli(self):
        m = self.out(self.ok("--ro", "project:other"), "XMOUNTS")
        self.assertEqual(m, ["-v", f"{self.t}/Projects/other:/ref/other:ro"])

    def test_project_ref_errors(self):
        for ref, msg in (("project:nope", "no such project"), ("project:dup", "more than once"),
                         ("project:../x", "bad project name"), ("project:", "bad project name"),
                         ("agents:a/b", "bad project name"), ("agents:.x", "bad project name"),
                         ("agents:nope", "is not a folder")):
            self.fails(msg, "--ro", ref)

    def test_agents_symlink_refused(self):
        os.symlink(f"{self.agents}/other", f"{self.agents}/link")
        self.fails("is not a folder", "--ro", "agents:link")

    def test_raw_path_into_agent_copies_refused(self):
        self.fails("overlaps the agent copies", "--ro", f"{self.agents}/other")
        self.fails("overlaps the agent copies", "--ro", self.agents)

    def test_agents_ref_keeps_other_protections(self):
        cfg2 = f"{self.agents}/cfgdir"
        os.rename(self.cfg, cfg2)
        self.env["AB_CONFIG"] = cfg2
        self.fails("overlaps protected path", "--ro", "agents:cfgdir")

    def test_agents_ref_refuses_context_root(self):
        ctx = f"{self.agents}/ctxdir"
        os.makedirs(f"{ctx}/projects/secret")
        self.env["AB_CONTEXT"] = ctx
        self.fails("overlaps protected path", "--ro", "agents:ctxdir")

    def test_raw_path_into_context_refused(self):
        os.makedirs(f"{self.t}/ctx/projects/secret")
        self.fails("overlaps protected path", "--ro", f"{self.t}/ctx/projects")


if __name__ == "__main__":
    unittest.main()
