"""A branch that must not be merged yet has a file HOLD, and what has to pass before a merge is red as long as it is there."""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOT_PLAIN = "Not to be merged yet: HOLD is not a plain file."


class Hold(unittest.TestCase):
    def go(self, files):
        """Starts the real script from another folder, with a stand-in for Python. What it says after everything else has run."""
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            scripts, python = root / ".github" / "scripts", root / "build" / "venv" / "bin" / "python"
            scripts.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            shutil.copy(ROOT / ".github" / "scripts" / "tests.sh", scripts)
            (scripts / "prepare.sh").write_text("")
            python.write_text("#!/bin/sh\necho has run\n")
            python.chmod(0o755)
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.symlink_to(text[2:]) if text.startswith("->") else path.write_text(text)
            done = subprocess.run(["bash", str(scripts / "tests.sh")], cwd="/", env={"PATH": os.environ["PATH"]}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            *before, last = done.stdout.splitlines()
            self.assertGreater(len(before), 5)
            self.assertEqual(set(before), {"has run"})
            return done.returncode, last

    def test_a_branch_that_has_to_wait_is_red_in_the_end(self):
        for text, said in (("Waits for run.sh, until 25 November.\nmore\n", "Waits for run.sh, until 25 November."), ("no line end", "no line end"), ("", "")):
            with self.subTest(text):
                self.assertEqual(self.go({"HOLD": text}), (1, f"Not to be merged yet: {said}"))

    def test_a_link_makes_it_wait_and_is_not_followed(self):
        for target in ("other", "nowhere", "a"):
            with self.subTest(target):
                self.assertEqual(self.go({"HOLD": "->" + target, "other": "private\n", "a/x": "x"}), (1, NOT_PLAIN))

    def test_a_folder_makes_it_wait(self):
        self.assertEqual(self.go({"HOLD/x": "x"}), (1, NOT_PLAIN))

    def test_only_that_file_makes_it_wait(self):
        self.assertEqual(self.go({}), (0, "has run"))
        self.assertEqual(self.go({"HOLDER": "x", "a/HOLD": "x"}), (0, "has run"))


if __name__ == "__main__":
    unittest.main()
