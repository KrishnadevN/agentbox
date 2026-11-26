"""Tests for lib/projects.py (run: python3 -m unittest discover -s tests)."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import projects  # noqa: E402
from projects import discover, lookup  # noqa: E402


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.t = os.path.realpath(self._tmp.name)
        self.root = os.path.join(self.t, "Projects")
        self.agents = os.path.join(self.t, "agents")
        os.makedirs(self.root)
        os.makedirs(self.agents)

    def tearDown(self):
        self._tmp.cleanup()

    def repo(self, rel, base=None):
        d = os.path.join(base or self.root, rel)
        os.makedirs(os.path.join(d, ".git"), exist_ok=True)
        return d

    def find(self, root=None):
        return discover(root or self.root, [self.agents])

    def test_flat_and_nested_with_category_and_group(self):
        self.repo("flat")
        self.repo("research/two")
        self.repo("research/Big/Big-manuscript")
        self.repo("a/b/c/deep4")
        p, dups = self.find()
        self.assertEqual(dups, {})
        self.assertEqual((p["flat"].category, p["flat"].group), ("", ""))
        self.assertEqual((p["two"].category, p["two"].group), ("research", ""))
        self.assertEqual((p["Big-manuscript"].category, p["Big-manuscript"].group), ("research", "Big"))
        self.assertEqual((p["deep4"].category, p["deep4"].group), ("a", "c"))

    def test_depth_limit(self):
        self.repo("a/b/c/d/deep5")
        self.assertNotIn("deep5", self.find()[0])

    def test_stops_at_git_and_ignores_nested_repo(self):
        self.repo("outer")
        self.repo("outer/inner")
        p, _ = self.find()
        self.assertIn("outer", p)
        self.assertNotIn("inner", p)

    def test_git_file_is_a_boundary_not_a_project(self):
        d = os.path.join(self.root, "linked-wt")
        os.makedirs(d)
        with open(os.path.join(d, ".git"), "w") as f:
            f.write("gitdir: /elsewhere/.git/worktrees/wt\n")
        self.repo("linked-wt/below")
        p, _ = self.find()
        self.assertNotIn("linked-wt", p)
        self.assertNotIn("below", p)

    def test_git_symlink_is_a_boundary_not_a_project(self):
        other = self.repo("other")
        d = os.path.join(self.root, "shares-git")
        os.makedirs(d)
        os.symlink(os.path.join(other, ".git"), os.path.join(d, ".git"))
        p, _ = self.find()
        self.assertIn("other", p)
        self.assertNotIn("shares-git", p)

    def test_fifo_git_is_not_a_marker(self):
        os.makedirs(os.path.join(self.root, "cat"))
        os.mkfifo(os.path.join(self.root, "cat", ".git"))
        self.repo("cat/real")
        p, _ = self.find()
        self.assertNotIn("cat", p)
        self.assertIn("real", p)

    def test_hidden_folders_skipped(self):
        self.repo(".hidden/repo")
        self.repo(".dotrepo")
        p, _ = self.find()
        self.assertNotIn("repo", p)
        self.assertNotIn(".dotrepo", p)

    def test_symlinked_folders_not_followed(self):
        outside = self.repo("ext", base=self.t)
        self.repo("cat2/inner", base=self.t)
        os.symlink(outside, os.path.join(self.root, "linked-repo"))
        os.symlink(os.path.join(self.t, "cat2"), os.path.join(self.root, "linked-cat"))
        p, _ = self.find()
        self.assertNotIn("linked-repo", p)
        self.assertNotIn("inner", p)

    def test_symlinked_root_works(self):
        self.repo("r")
        link = os.path.join(self.t, "ProjectsLink")
        os.symlink(self.root, link)
        self.assertIn("r", self.find(link)[0])

    def test_root_inside_agent_copies_refused(self):
        self.repo("victim", base=self.agents)
        link = os.path.join(self.t, "ProjectsLink")
        os.symlink(self.agents, link)
        self.assertEqual(self.find(link), ({}, {}))
        self.assertIsNotNone(projects.root_problem(link, [self.agents]))

    def test_agent_tree_inside_root_skipped(self):
        agents = os.path.join(self.root, "agentcopies")
        self.repo("victim", base=agents)
        self.assertNotIn("victim", discover(self.root, [agents])[0])

    def test_three_repos_one_name_all_reported(self):
        paths = [self.repo("same"), self.repo("x/same"), self.repo("y/z/same")]
        p, dups = self.find()
        self.assertNotIn("same", p)
        self.assertEqual(sorted(dups["same"]), sorted(paths))
        _, err = lookup("same", (p, dups), root=self.root)
        for path in paths:
            self.assertIn(path, err)

    def test_lookup_unknown(self):
        proj, err = lookup("nope", self.find(), root=self.root)
        self.assertIsNone(proj)
        self.assertIn("no such project", err)

    def test_bad_tags_ignored(self):
        cfg = os.path.join(self.t, "cfg")
        os.makedirs(os.path.join(cfg, "projects"))
        with open(os.path.join(cfg, "projects", "x.toml"), "w") as f:
            f.write("[project]\ntags = 1\n")
        old, projects.CONFIG = projects.CONFIG, cfg
        try:
            self.assertEqual(projects._tags("x"), [])
        finally:
            projects.CONFIG = old


if __name__ == "__main__":
    unittest.main()
