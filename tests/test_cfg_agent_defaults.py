"""Shared agent defaults (~/.agents-context/agents/<agent>/) and the Claude token file.
Run: python3 -m unittest discover -s tests"""
import os, shlex, socket, subprocess, tempfile, unittest

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "cfg.py")
HOST = socket.gethostname().split(".")[0]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class AgentDefaultsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self.t = os.path.realpath(self._tmp.name)
        self.cfg, self.ctx, self.state = f"{t}/cfg", f"{t}/ctx", f"{t}/state"
        os.makedirs(f"{t}/Projects/proj/.git")
        os.makedirs(f"{t}/home")
        write(f"{self.cfg}/hosts/{HOST}.toml", "")
        self.env = dict(os.environ, HOME=f"{t}/home", AB_CONFIG=self.cfg, AB_PROJECTS=f"{t}/Projects",
                        AB_AGENTS=f"{t}/agents", AB_STATE=self.state, AB_CONTEXT=self.ctx)
        self.env.pop("AB_CFG_QUIET", None)

    def tearDown(self):
        self._tmp.cleanup()

    def run_cfg(self):
        return subprocess.run(["python3", CFG, "proj"], capture_output=True, text=True, env=self.env)

    def ok(self):
        r = self.run_cfg()
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def fails(self, msg):
        r = self.run_cfg()
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(msg, r.stderr)

    def out(self, r, key):
        line = next(l for l in r.stdout.splitlines() if l.startswith(key + "="))
        return shlex.split(line.split("=", 1)[1])

    def test_defaults_only_when_folder_exists(self):
        self.assertEqual(self.out(self.ok(), "DEFAULTS_claude"), [""])
        os.makedirs(f"{self.ctx}/agents/claude")
        r = self.ok()
        self.assertEqual(self.out(r, "DEFAULTS_claude"), [f"{self.ctx}/agents/claude"])
        self.assertEqual(self.out(r, "DEFAULTS_codex"), [""])

    def test_symlinked_context_root_is_fine(self):
        os.makedirs(f"{self.t}/realctx/agents/claude")
        os.symlink(f"{self.t}/realctx", self.ctx)
        self.assertEqual(self.out(self.ok(), "DEFAULTS_claude"), [f"{self.t}/realctx/agents/claude"])

    def test_symlinked_defaults_refused(self):
        os.makedirs(f"{self.t}/elsewhere")
        os.makedirs(f"{self.ctx}/agents")
        os.symlink(f"{self.t}/elsewhere", f"{self.ctx}/agents/claude")
        self.fails("must be a folder")

    def test_symlinked_agents_folder_refused(self):
        os.makedirs(f"{self.t}/elsewhere/claude")
        os.makedirs(self.ctx)
        os.symlink(f"{self.t}/elsewhere", f"{self.ctx}/agents")
        self.fails("must be a folder")

    def test_file_instead_of_folder_refused(self):
        write(f"{self.ctx}/agents/claude", "x")
        self.fails("must be a folder")

    def test_other_protections_kept(self):
        os.makedirs(f"{self.ctx}/agents/claude")
        os.rename(self.cfg, f"{self.ctx}/agents/claude/cfg")
        self.env["AB_CONFIG"] = f"{self.ctx}/agents/claude/cfg"
        self.fails("overlaps protected path")

    def test_config_and_context_on_same_folder_refused(self):
        os.makedirs(f"{self.ctx}/agents/claude")
        os.rename(f"{self.cfg}/hosts", f"{self.ctx}/hosts")
        self.env["AB_CONFIG"] = self.ctx                        # both roots in one folder
        self.fails("overlaps protected path")

    def test_hash_follows_folder_and_token_not_contents(self):
        def h():
            return self.out(self.ok(), "CFGHASH")[0]
        h0 = h()
        os.makedirs(f"{self.ctx}/agents/claude")
        h1 = h()
        write(f"{self.ctx}/agents/claude/settings.json", "{}")       # copied on next launch
        self.assertEqual(h(), h1)
        os.rename(f"{self.ctx}/agents/claude", f"{self.ctx}/agents/old")   # replaced folder
        os.makedirs(f"{self.ctx}/agents/claude")
        h2 = h()
        write(f"{self.state}/auth/claude.env", "CLAUDE_CODE_OAUTH_TOKEN=a\n")
        h3 = h()
        write(f"{self.state}/auth/claude.env", "CLAUDE_CODE_OAUTH_TOKEN=b\n")
        h4 = h()
        self.assertEqual(len({h0, h1, h2, h3, h4}), 5)

    def test_token_name_reserved_in_env(self):
        write(f"{self.cfg}/projects/proj.toml", '[project]\nenv = { CLAUDE_CODE_OAUTH_TOKEN = "x" }\n')
        r = self.ok()
        self.assertIn("env: CLAUDE_CODE_OAUTH_TOKEN ignored", r.stderr)
        self.assertIn("ENV_ARGS=()", r.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
