"""What the README says in numbers is counted, and each row of the contract has a test that carries its number."""

import pathlib
import re
import unittest

import looks
import wrong
import wrong_rules

ROOT = pathlib.Path(__file__).resolve().parents[1]
LATER = "*Comes with the totals*"


def rows_of(contract):
    """The rows of what can happen, by their numbers: what must be true then."""
    return {int(number): must for number, must in re.findall(r"^\| ([0-9]+) \| [^|]+ \| ([^|]+) \|$", contract.split("## What can happen")[1], re.MULTILINE)}


def without_test(contract, tests):
    """The rows that have no test with their number, and those that have one although they say that they come later."""
    return [number for number, must in rows_of(contract).items() if bool(re.search(rf"def test_{number:02}_", tests)) != (must != LATER)]


def unnamed(mistakes):
    """The tests that no mistake names."""
    named = {test for one in mistakes for test in one.noticed_by}
    written = {
        f"{of_it}.{name}" for of_it in wrong_rules.CLASSES.values()
        for name in re.findall(r"^    def (test_[a-z0-9_]+)\(self", (ROOT / "tests" / f"{of_it.split('.')[0]}.py").read_text(encoding="utf-8"), re.MULTILINE)
    }
    return sorted(written - named)


class Told(unittest.TestCase):
    def setUp(self):
        self.contract = (ROOT / "docs" / "contract.md").read_text(encoding="utf-8")
        self.tests = "".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "tests").glob("test_*.py")))

    def test_what_the_readme_counts(self):
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        examples = looks.examples()
        known = {how: sum(example.known == how for example in examples) for how in ("test", "run")}
        for said in (
            f"[{len(examples)} bodies]", f"The answers of {known['test']} stand in", f"The other {known['run']} were asked there once",
            f"{len(rows_of(self.contract))} things that can happen", f"[{len(wrong.ALL)} mistakes](tests/wrong.py)",
            f"[{len(wrong_rules.EVERY_ONE)}](tests/wrong_rules.py)",
        ):
            with self.subTest(said):
                self.assertIn(said, readme)

    def test_each_row_has_a_test(self):
        self.assertEqual(list(rows_of(self.contract)), list(range(1, len(rows_of(self.contract)) + 1)))
        self.assertEqual(without_test(self.contract, self.tests), [])

    def test_each_test_is_named_by_a_mistake(self):
        """A test that no mistake has made red may be one that cannot fail."""
        self.assertEqual(unnamed(wrong_rules.EVERY_ONE), [])
        self.assertEqual(unnamed([one for one in wrong_rules.EVERY_ONE if "test_rows.Rows.test_13_a_day_with_25_hours" not in one.noticed_by]), ["test_rows.Rows.test_13_a_day_with_25_hours"])

    def test_the_check_can_fail(self):
        row = next(line for line in self.contract.splitlines() if line.startswith("| 7 |"))
        self.assertEqual(without_test(self.contract + row.replace("| 7 |", "| 99 |") + "\n", self.tests), [99])
        self.assertEqual(without_test(self.contract, self.tests.replace("def test_16_", "def test_")), [16])
        self.assertEqual(without_test(self.contract.replace("| Spoiled |", f"| {LATER} |"), self.tests), [1])


if __name__ == "__main__":
    unittest.main()
