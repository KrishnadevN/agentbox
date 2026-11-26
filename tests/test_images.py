"""Tests for layer resolution in lib/images.py (run: python3 -m unittest discover -s tests)."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import images  # noqa: E402


class ImagesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pkg = os.path.join(self._tmp.name, "pkg")
        self.usr = os.path.join(self._tmp.name, "usr")
        self._dirs, images.DIRS = images.DIRS, [self.pkg, self.usr]

    def tearDown(self):
        images.DIRS = self._dirs
        self._tmp.cleanup()

    def define(self, toml, layers=(), user_layers=()):
        os.makedirs(self.pkg, exist_ok=True)
        with open(os.path.join(self.pkg, "profiles.toml"), "w") as f:
            f.write(toml)
        for n in layers:
            os.makedirs(os.path.join(self.pkg, n), exist_ok=True)
        for n in user_layers:
            os.makedirs(os.path.join(self.usr, n), exist_ok=True)
        return images.profiles()

    BASE = '[base]\nfrom = "x"\n[web]\nparent = "base"\n'

    def names(self, dirs):
        return [d.replace(self._tmp.name + "/", "") for d in dirs]

    def test_dependency_order_and_user_folders(self):
        prof = self.define(self.BASE + '[fonts]\nparent = "base"\n'
                           '[docs]\nparent = "base"\ninclude = ["fonts"]\n'
                           '[webdocs]\nparent = "web"\ninclude = ["docs"]\n',
                           layers=["fonts", "docs", "webdocs"], user_layers=["docs"])
        self.assertEqual(self.names(images.layer_dirs(prof, "webdocs")),
                         ["pkg/fonts", "pkg/docs", "usr/docs", "pkg/webdocs"])

    def test_each_layer_once(self):
        prof = self.define(self.BASE + '[a]\nparent = "base"\n[b]\nparent = "base"\ninclude = ["a"]\n'
                           '[c]\nparent = "base"\ninclude = ["a", "b"]\n', layers=["a", "b", "c"])
        self.assertEqual(images.applied(prof, "c"), ["a", "b", "c"])

    def test_loops_rejected(self):
        for toml in ('[a]\nparent = "base"\ninclude = ["b"]\n[b]\nparent = "base"\ninclude = ["a"]\n',
                     '[a]\nparent = "base"\ninclude = ["a"]\n'):
            prof = self.define(self.BASE + toml)
            with self.assertRaises(SystemExit):
                images.applied(prof, "a")

    def test_unknown_include_rejected(self):
        with self.assertRaises(SystemExit):
            self.define(self.BASE + '[a]\nparent = "base"\ninclude = ["nope"]\n')

    def test_include_must_be_a_list(self):
        with self.assertRaises(SystemExit):
            self.define(self.BASE + '[a]\nparent = "base"\ninclude = "web"\n')

    def test_include_of_a_parent_rejected(self):
        prof = self.define(self.BASE + '[a]\nparent = "web"\ninclude = ["base"]\n')
        with self.assertRaises(SystemExit):
            images.supplied(prof, "a")

    def test_parent_already_includes_it(self):
        prof = self.define(self.BASE + '[docs]\nparent = "base"\n[p]\nparent = "base"\ninclude = ["docs"]\n'
                           '[c]\nparent = "p"\ninclude = ["docs"]\n')
        with self.assertRaises(SystemExit):
            images.layer_dirs(prof, "c")

    def test_parent_includes_the_child_itself(self):
        prof = self.define('[base]\nfrom = "x"\ninclude = ["child"]\n[child]\nparent = "base"\n')
        with self.assertRaises(SystemExit):
            images.supplied(prof, "child")

    def test_parent_loop_reported_by_uses(self):
        prof = self.define('[base]\nfrom = "x"\n[a]\nparent = "b"\n[b]\nparent = "a"\n')
        with self.assertRaises(SystemExit):
            images.uses(prof, "a", "docs")

    def test_uses_through_parent_and_include(self):
        prof = self.define(self.BASE + '[docs]\nparent = "base"\n[webdocs]\nparent = "web"\ninclude = ["docs"]\n'
                           '[thesis]\nparent = "docs"\n')
        self.assertTrue(images.uses(prof, "webdocs", "docs"))
        self.assertTrue(images.uses(prof, "thesis", "docs"))
        self.assertFalse(images.uses(prof, "web", "docs"))

    def test_named_plan_builds_only_the_layer(self):
        prof = self.define(self.BASE + '[docs]\nparent = "base"\n[webdocs]\nparent = "web"\ninclude = ["docs"]\n',
                           layers=["docs", "webdocs"])
        built = {"base", "web"}           # docs has no image
        plan = images.plan(prof, ["webdocs"], lambda n: n in built, named=True)
        self.assertEqual([p[0] for p in plan], ["webdocs"])
        self.assertEqual(plan[0][1], images.image("web"))
        self.assertEqual(self.names(plan[0][2]), ["pkg/docs", "pkg/webdocs"])


if __name__ == "__main__":
    unittest.main()
