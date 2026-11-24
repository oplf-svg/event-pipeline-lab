"""The README says whose portfolio this is and who made what, with the one name that stands in NOTICE. The licence is Apache's."""

import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOT_OURS = {".git", "build", "__pycache__", ".venv"}
# Written in two pieces, so that this file does not find itself.
PLACES = ("OWNER_" + "NAME", "SITE_" + "ADDRESS")
APACHE_2 = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
WHOSE = "Part of the public portfolio of {}."
WHO = (
    "Directed and approved by {}. Code, tests and texts are written by Claude, an AI agent that proposes its changes under an "
    "identity of its own."
)
# What nobody has proven, or what is not so, however good it sounds.
TOO_MUCH = re.compile(r"cannot approve|cannot merge|approve or merge one|designed by|built by|reviewed by", re.IGNORECASE)
REPOSITORIES = "(https://github.com/oplf-svg)"


def name_in(notice):
    """The one copyright line of NOTICE. Nowhere else is the name decided."""
    found = re.findall(r"^Copyright [0-9]{4} (\S.*\S)$", notice, re.MULTILINE)
    return found[0] if len(found) == 1 else None


def problems(readme, notice):
    name, lines = name_in(notice), readme.splitlines()
    if not name:
        return ["NOTICE has no name, or more than one"]
    found = [] if len(lines) > 2 and lines[2].startswith(WHOSE.format(name)) else ["line 3 does not say whose portfolio this is"]
    if REPOSITORIES not in "\n".join(lines[:5]):
        found.append("there is no link to the other repositories")
    if WHO.format(name) not in " ".join(readme.split()):
        found.append("it does not say who made this, word for word")
    if TOO_MUCH.search(" ".join(readme.split())):
        found.append("it says more than is true")
    return found + [f"a name is missing: {place}" for place in PLACES if place in readme + notice]


class Readme(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

    def test_it_says_whose_it_is_and_who_made_it(self):
        self.assertEqual(problems(self.readme, self.notice), [])

    def test_the_check_can_fail(self):
        name = name_in(self.notice)
        line = self.readme.splitlines()[2]
        for what, (readme, notice) in {
            "line 3 is gone": (self.readme.replace(line, ""), self.notice),
            "line 3 stands further down": (self.readme.replace(line, "\n" * 5 + line), self.notice),
            "the link is gone": (self.readme.replace(REPOSITORIES, ""), self.notice),
            "another name in line 3": (self.readme.replace(line, line.replace(name, "Somebody Else")), self.notice),
            "another name at the end": (self.readme.replace("approved by " + name, "approved by Somebody Else"), self.notice),
            "other words": (self.readme.replace("Directed and approved", "Designed and built"), self.notice),
            "more than is true": (self.readme + "It cannot approve\nits own work.\n", self.notice),
            "another name in NOTICE": (self.readme, self.notice.replace(name, "Somebody Else")),
            "no name in NOTICE": (self.readme, self.notice.replace(name, "")),
            "two names in NOTICE": (self.readme, self.notice + "Copyright 2026 Somebody Else\n"),
            **{f"{place} is left": (self.readme + place, self.notice) for place in PLACES},
        }.items():
            with self.subTest(what):
                self.assertNotEqual((readme, notice), (self.readme, self.notice))
                self.assertTrue(problems(readme, notice))

    def test_the_licence_is_apache_2_letter_by_letter(self):
        self.assertEqual(hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest(), APACHE_2)

    def test_nothing_holds_a_place_anywhere(self):
        for path in ROOT.rglob("*"):
            if path.is_file() and not NOT_OURS & set(path.relative_to(ROOT).parts):
                text = path.read_text(encoding="utf-8", errors="replace")
                for place in PLACES:
                    with self.subTest(str(path.relative_to(ROOT))):
                        self.assertFalse(place in text, f"{place} is still in it")


if __name__ == "__main__":
    unittest.main()
