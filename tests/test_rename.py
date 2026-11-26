"""agentbox rename: checks before anything moves, no-overwrite moves, git remote update.
Run: python3 -m unittest discover -s tests"""
import os, subprocess, sys, tempfile, unittest

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
RENAME = os.path.join(LIB, "rename.py")


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class RenameTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = self.t = os.path.realpath(self._tmp.name)
        self.agents, self.state, self.ctx, self.cfg = f"{t}/agents", f"{t}/state", f"{t}/ctx", f"{t}/cfg"
        # stub podman: `pod exists ab-<name>` exits with the number in pods/<name> (default 1)
        os.makedirs(f"{t}/bin")
        os.makedirs(f"{t}/pods")
        write(f"{t}/bin/podman", '#!/bin/sh\nf="%s/pods/${3#ab-}"\nif [ -f "$f" ]; then read -r c < "$f"; exit "$c"; fi\nexit 1\n' % t)
        os.chmod(f"{t}/bin/podman", 0o755)
        self.env = dict(os.environ, HOME=f"{t}/home", AB_PROJECTS=f"{t}/Projects", AB_AGENTS=self.agents,
                        AB_STATE=self.state, AB_CONTEXT=self.ctx, AB_CONFIG=self.cfg,
                        PATH=f"{t}/bin:{os.environ['PATH']}",
                        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        self.repo = f"{t}/Projects/cat/new"
        self.git("init", "-q", self.repo)
        self.git("-C", self.repo, "remote", "add", "agent", f"{self.agents}/old")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], check=True, env=self.env, capture_output=True)

    def old_state(self, which=range(7)):
        paths = self.paths("old")
        for i in which:
            p = paths[i]
            if p.endswith((".md", ".toml")):
                write(p, f"marker {i}")
            else:
                write(f"{p}/marker", f"marker {i}")
        return paths

    def paths(self, n):
        return [f"{self.agents}/{n}", f"{self.state}/bridge/{n}.git", f"{self.state}/home/{n}",
                f"{self.state}/ctx/{n}", f"{self.ctx}/projects/{n}",
                f"{self.ctx}/project-instructions/{n}.md", f"{self.cfg}/projects/{n}.toml"]

    def run_rename(self, old="old", new="new"):
        return subprocess.run([sys.executable, RENAME, old, new], capture_output=True, text=True, env=self.env)

    def remote(self):
        return subprocess.run(["git", "-C", self.repo, "remote", "get-url", "agent"], capture_output=True,
                              text=True, env=self.env).stdout.strip()

    def refused(self, msg, old="old", new="new"):
        before = {p: os.path.lexists(p) for p in self.paths(old) + self.paths(new)}
        r = self.run_rename(old, new)
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(msg, r.stderr)
        self.assertEqual(before, {p: os.path.lexists(p) for p in before}, "something moved")

    def read(self, p):
        with open(p if p.endswith((".md", ".toml")) else f"{p}/marker") as f:
            return f.read()

    def test_full_rename(self):
        self.old_state()
        r = self.run_rename()
        self.assertEqual(r.returncode, 0, r.stderr)
        for i, (o, n) in enumerate(zip(self.paths("old"), self.paths("new"))):
            self.assertFalse(os.path.lexists(o), o)
            self.assertEqual(self.read(n), f"marker {i}")
        self.assertEqual(self.remote(), f"{self.agents}/new")

    def test_only_existing_sources_move(self):
        self.old_state([0, 2])
        r = self.run_rename()
        self.assertEqual(r.returncode, 0, r.stderr)
        new = self.paths("new")
        self.assertEqual([os.path.lexists(p) for p in new], [True, False, True, False, False, False, False])

    def test_leftover_destinations_refused_even_without_source(self):
        self.old_state([0])
        write(f"{self.cfg}/projects/new.toml", "leftover")
        self.refused(f"{self.cfg}/projects/new.toml")
        os.remove(f"{self.cfg}/projects/new.toml")
        os.makedirs(f"{self.state}/home")
        os.symlink(f"{self.t}/nowhere", f"{self.state}/home/new")            # dangling symlink
        self.refused(f"{self.state}/home/new")

    def test_bad_names_refused(self):
        self.old_state([0])
        for bad in ("", "a/b", ".x", "-x", "paper draft"):
            self.refused("cannot be a project name", new=bad)
        for bad in ("list", "rename"):
            self.refused("is in RESERVED_NAMES", new=bad)
        for bad in ("", "a/b", ".x"):
            self.refused("bad old name", old=bad)
        self.refused("same", new="old")

    def test_underscore_name_accepted(self):
        os.rename(self.repo, f"{self.t}/Projects/cat/_paper")
        self.repo = f"{self.t}/Projects/cat/_paper"
        self.old_state([0])
        r = self.run_rename(new="_paper")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_pods_checked(self):
        self.old_state([0])
        write(f"{self.t}/pods/old", "0")
        self.refused("agentbox-down old")
        os.remove(f"{self.t}/pods/old")
        write(f"{self.t}/pods/new", "0")
        self.refused("agentbox-down new")
        write(f"{self.t}/pods/new", "125")
        self.refused("podman exit 125")

    def test_discovery_checked(self):
        self.old_state([0])
        os.makedirs(f"{self.t}/Projects/old/.git")
        self.refused("rename the folder to 'new' first")                    # folder not renamed
        os.makedirs(f"{self.t}/Projects/x")
        os.rename(f"{self.t}/Projects/old", f"{self.t}/Projects/x/old")
        os.makedirs(f"{self.t}/Projects/y/old/.git")
        self.refused("still a project")                                    # old as a duplicate
        subprocess.run(["rm", "-rf", f"{self.t}/Projects/x", f"{self.t}/Projects/y"], check=True)
        os.makedirs(f"{self.t}/Projects/other/new/.git")
        self.refused("more than once")                                     # new duplicated
        subprocess.run(["rm", "-rf", f"{self.t}/Projects/other"], check=True)
        self.refused("no such project", new="missing")

    def test_no_agent_copy(self):
        self.old_state([2])
        self.refused("nothing to rename")

    def test_migrate_from_reserved_name(self):
        write(f"{self.agents}/rename/marker", "m")
        r = self.run_rename(old="rename")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isdir(f"{self.agents}/new"))

    def test_move_never_overwrites(self):
        sys.path.insert(0, LIB)
        import rename
        write(f"{self.t}/src/x", "src")
        write(f"{self.t}/dst/x", "dst")                 # appeared after the checks
        with self.assertRaises(FileExistsError):
            rename.move(f"{self.t}/src", f"{self.t}/dst")
        with open(f"{self.t}/dst/x") as f:
            self.assertEqual(f.read(), "dst")
        self.assertTrue(os.path.exists(f"{self.t}/src/x"))

    def test_remote_failure_prints_attempted_command(self):
        for has_remote in (True, False):
            with self.subTest(has_remote=has_remote):
                if not has_remote:
                    self.git("-C", self.repo, "remote", "remove", "agent")
                self.old_state([0])
                write(f"{self.repo}/.git/config.lock")
                r = self.run_rename()
                os.remove(f"{self.repo}/.git/config.lock")
                self.assertNotEqual(r.returncode, 0)
                verb = "set-url" if has_remote else "add"
                self.assertIn(f"run: git -C {self.repo} remote {verb} agent {self.agents}/new", r.stderr)
                self.assertTrue(os.path.isdir(f"{self.agents}/new"))           # moves done
                os.rename(f"{self.agents}/new", f"{self.agents}/old")         # reset for the next case

    def test_no_git_refused_before_moving(self):
        self.old_state([0])
        self.env["PATH"] = f"{self.t}/bin"                  # stub podman only, no git
        self.refused("cannot run git")

    def test_broken_git_config_refused_before_moving(self):
        self.old_state([0])
        with open(f"{self.repo}/.git/config", "a") as f:
            f.write("[broken\n")
        self.refused("git cannot read")

    def test_git_failing_after_moves_prints_command(self):
        self.old_state([0])
        # a git that lists the remote once, then disappears (cannot be started any more)
        write(f"{self.t}/bin/git", '#!/bin/sh\n/bin/rm -- "$0"\necho agent\n')
        os.chmod(f"{self.t}/bin/git", 0o755)
        self.env["PATH"] = f"{self.t}/bin"
        r = self.run_rename()
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(f"run: git -C {self.repo} remote set-url agent {self.agents}/new", r.stderr)
        self.assertTrue(os.path.isdir(f"{self.agents}/new"))

    def test_lookup_refuses_unusable_folders(self):
        for name, msg in (("list", "RESERVED_NAMES"), ("paper draft", "cannot be a project name")):
            os.makedirs(f"{self.t}/Projects/{name}/.git")
            out = subprocess.run([sys.executable, os.path.join(LIB, "projects.py"), "path", name],
                                 capture_output=True, text=True, env=self.env)
            self.assertNotEqual(out.returncode, 0)
            self.assertIn(msg, out.stderr)


if __name__ == "__main__":
    unittest.main()
