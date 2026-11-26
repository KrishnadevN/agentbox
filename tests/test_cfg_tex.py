"""TeX Live mount: layers that use docs get it; the mounted folder is checked.
Run: python3 -m unittest discover -s tests"""
import os, shlex, socket, subprocess, tempfile, unittest

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib", "cfg.py")


class TexMountTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = os.path.realpath(self._tmp.name)
        self.t, self.home = t, os.path.join(t, "home")
        self.cfg = os.path.join(t, "cfg")
        os.makedirs(os.path.join(t, "Projects", "paper", ".git"))
        for d in ("projects", "hosts", "images"):
            os.makedirs(os.path.join(self.cfg, d))
        os.makedirs(self.home)
        with open(os.path.join(self.cfg, "images", "profiles.toml"), "w") as f:
            f.write('[webdocs]\nparent = "web"\ninclude = ["docs"]\n')
        with open(os.path.join(self.cfg, "projects", "paper.toml"), "w") as f:
            f.write('[project]\nprofile = "webdocs"\n')
        self.env = dict(os.environ, HOME=self.home, AB_CONFIG=self.cfg, AB_PROJECTS=f"{t}/Projects",
                        AB_AGENTS=f"{t}/agents", AB_STATE=f"{t}/state", AB_CONTEXT=f"{t}/ctx",
                        AB_CFG_QUIET="1")

    def tearDown(self):
        self._tmp.cleanup()

    def run_cfg(self, tex_root):
        os.makedirs(tex_root, exist_ok=True)
        host = socket.gethostname().split(".")[0]
        with open(os.path.join(self.cfg, "hosts", f"{host}.toml"), "w") as f:
            f.write(f'[host]\ntex_root = "{tex_root}"\n')
        return subprocess.run(["python3", CFG, "paper"], capture_output=True, text=True, env=self.env)

    def out(self, r, key):
        line = next(l for l in r.stdout.splitlines() if l.startswith(key + "="))
        return shlex.split(line.split("=", 1)[1])[0]

    def test_webdocs_gets_the_tex_mount(self):
        r = self.run_cfg(os.path.join(self.t, "texlive", "2026"))
        self.assertEqual(r.returncode, 0, r.stderr)
        tl = os.path.join(self.t, "texlive")
        self.assertIn(f"{tl}:{tl}:ro", r.stdout)
        self.assertEqual(self.out(r, "TEX_ROOT"), f"{tl}/2026")
        self.assertEqual(self.out(r, "SRC"), os.path.join(self.t, "Projects", "paper"))

    def test_symlinked_tex_parent_mounted_where_tex_root_points(self):
        real = os.path.join(self.t, "real-texlive")
        os.makedirs(os.path.join(real, "2026"))
        os.symlink(real, os.path.join(self.t, "texlive"))
        r = self.run_cfg(os.path.join(self.t, "texlive", "2026"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"{real}:{real}:ro", r.stdout)
        self.assertEqual(self.out(r, "TEX_ROOT"), f"{real}/2026")

    def test_tex_root_whose_parent_is_home_refused(self):
        r = self.run_cfg(os.path.join(self.home, "texlive"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing to mount", r.stderr)


if __name__ == "__main__":
    unittest.main()
