"""Tests for lib/safe_mkdir.py (run: python3 -m unittest discover -s tests)."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
from safe_mkdir import safe_mkdir, safe_touch  # noqa: E402


class SafeMkdirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = os.path.join(self._tmp.name, "base")
        self.outside = os.path.join(self._tmp.name, "outside")
        os.mkdir(self.base)
        os.mkdir(self.outside)

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *parts):
        return os.path.join(self.base, *parts)

    def test_creates_nested_folders(self):
        safe_mkdir(self.base, "a/b/c/")
        self.assertTrue(os.path.isdir(self.p("a", "b", "c")))

    def test_refuses_symlink_component(self):
        os.symlink(self.outside, self.p("a"))
        with self.assertRaises(ValueError):
            safe_mkdir(self.base, "a/b")
        self.assertEqual(os.listdir(self.outside), [])

    def test_refuses_dotdot(self):
        with self.assertRaises(ValueError):
            safe_mkdir(self.base, "a/../../x")

    def test_touch_creates_empty_file_and_folders(self):
        safe_touch(self.base, "d/history.jsonl")
        self.assertTrue(os.path.isfile(self.p("d", "history.jsonl")))
        self.assertEqual(os.path.getsize(self.p("d", "history.jsonl")), 0)

    def test_touch_keeps_content(self):
        with open(self.p("f"), "w") as f:
            f.write("keep")
        safe_touch(self.base, "f")
        with open(self.p("f")) as f:
            self.assertEqual(f.read(), "keep")

    def test_touch_refuses_symlink_file(self):
        target = os.path.join(self.outside, "t")
        os.symlink(target, self.p("f"))
        with self.assertRaises(ValueError):
            safe_touch(self.base, "f")
        self.assertFalse(os.path.exists(target))

    def test_touch_refuses_symlink_parent(self):
        os.symlink(self.outside, self.p("d"))
        with self.assertRaises(ValueError):
            safe_touch(self.base, "d/f")
        self.assertEqual(os.listdir(self.outside), [])

    def test_touch_refuses_folder_and_fifo(self):
        os.mkdir(self.p("dir"))
        os.mkfifo(self.p("fifo"))
        for name in ("dir", "fifo"):
            with self.assertRaises(ValueError):
                safe_touch(self.base, name)


if __name__ == "__main__":
    unittest.main()
