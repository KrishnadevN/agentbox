"""agentbox-build applies setup scripts in folder order, also with ten or more folders.
Uses a fake podman (no containers). Run: python3 -m unittest discover -s tests"""
import os, subprocess, tempfile, unittest

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
FAKE = """#!/bin/bash
case "$1 $2" in
  "image exists") exit 0 ;;
  "--runtime crun") ctx=${@: -1}; for s in "$ctx"/layer/setup.d/*.sh; do cat "$s"; done >> "$FAKE_OUT" ;;
esac
exit 0
"""


class BuildOrderTest(unittest.TestCase):
    def test_setup_scripts_run_in_folder_order(self):
        with tempfile.TemporaryDirectory() as t:
            fake = os.path.join(t, "bin")
            os.makedirs(fake)
            with open(os.path.join(fake, "podman"), "w") as f:
                f.write(FAKE)
            os.chmod(os.path.join(fake, "podman"), 0o755)
            imgs = os.path.join(t, "cfg", "images")
            names = [f"l{i:02d}" for i in range(1, 12)]          # 11 included layers
            os.makedirs(imgs)
            with open(os.path.join(imgs, "profiles.toml"), "w") as f:
                for n in names:
                    f.write(f'[{n}]\nparent = "base"\n')
                f.write('[big]\nparent = "base"\ninclude = [' + ", ".join(f'"{n}"' for n in names) + "]\n")
            for n in names + ["big"]:
                os.makedirs(os.path.join(imgs, n))
                with open(os.path.join(imgs, n, "setup.sh"), "w") as f:
                    f.write(f"{n}\n")
            out = os.path.join(t, "order")
            env = dict(os.environ, PATH=f"{fake}:{os.environ['PATH']}", AB_CONFIG=os.path.join(t, "cfg"),
                       FAKE_OUT=out)
            subprocess.run([os.path.join(BIN, "agentbox-build"), "big"], check=True,
                           capture_output=True, env=env)
            with open(out) as f:
                self.assertEqual(f.read().split(), names + ["big"])


if __name__ == "__main__":
    unittest.main()
