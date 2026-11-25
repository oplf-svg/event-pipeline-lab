"""The rules are plain SQL. Whatever only some engines have, or what they mean in their own ways, is not in them.

That is a list of what is allowed, and not of what is not: a word, a function or a sign that nobody has thought of is refused.
"""

import re

from lab import ROOT, Lab, run

WORDS = set("select from left join cross on where group by order partition over rows between unbounded preceding current row and case when then else end as is not null in with distinct".split())
FUNCTIONS = {"count", "min", "max", "row_number", "first_value", "coalesce"}
GIVEN = {"arrived", "shop_days", "limits", "oldest_us", "future_us", *run.RULES, *(name for name, _ in run.ARRIVED + run.DAYS)}
PART = re.compile(r"\s+|'[^']+'|[a-z_][a-z0-9_]*|[0-9]+(?![.0-9a-z_])|<>|<=|>=|[=<>+(),.-]")
SIGNS = {"=", "<", ">", "<>", "<=", ">=", "+", "-"}


def statement(name):
    """A rule without what is said about it."""
    return re.sub(r"--[^\n]*", "", (ROOT / "rules" / name).read_text(encoding="utf-8")).lower()


def given(text):
    """The names that a rule itself gives to something."""
    return set(re.findall(r"\bas ([a-z_]+)", text)) | set(re.findall(r"\b([a-z_]+) as \(", text))


def not_plain(text, others=""):
    """Everything in it that not every engine means in the same way."""
    parts, at = [], 0
    while at < len(text):
        found = PART.match(text, at)
        if not found:
            return [f"the sign {text[at]}"]
        if not found[0].isspace():
            parts.append(found[0])
        at = found.end()
    names, problems = GIVEN | given(text) | given(others), []
    for before, part, after in zip(["", *parts], parts, [*parts[1:], ""], strict=False):
        word = re.fullmatch(r"[a-z_][a-z0-9_]*", part)
        if word and after == "(" and part not in WORDS and part not in FUNCTIONS:
            problems.append(f"the function {part}")
        elif word and len(part) > 1 and part not in WORDS | FUNCTIONS | names:
            problems.append(f"the word {part}")
        elif part in SIGNS and before in SIGNS:
            problems.append(f"the signs {before}{part}")
        elif part == "." and not before.isidentifier():
            problems.append("a fraction")
        elif part == "distinct" and before != "(":
            problems.append("distinct that is not inside of a count")
        elif part.isdigit() and before == "by":
            problems.append("a column by its number")
    return problems


class Rules(Lab):
    def test_they_are_plain(self):
        names = sorted(path.name for path in (ROOT / "rules").glob("*.sql"))
        self.assertEqual(names, sorted(f"{name}.sql" for name in run.RULES))
        for name in names:
            with self.subTest(name):
                self.assertEqual(not_plain(statement(name), "".join(map(statement, names))), [])

    def test_the_check_can_fail(self):
        for what in (
            "ifnull(a, b)", "date_trunc(a)", "lower(feed)", "shop::text", 'select "shop"', "`shop`", "[shop]", "shop || feed", "qualify n = 1", "select 1 limit 1", "select top 1", "shop = ''",
            "spoiled is true", "n / 2", "n % 2", "n * 2", "n > 1.5", "n > .5", "n > 1e3", "select *", "select a.*", "order by 1", "shop = ?", "shop = :shop", "shop = $1", "@shop", "full join arrived",
            "join arrived using (place)", "natural join arrived", "n == 2", "n != 2", "n <=> 2", "n = - 2", "n is not distinct from 2", "n is distinct from 2", "select distinct shop", "shop like 'n'",
            "order by n nulls last", "n = rowid", "current_timestamp", "now()", "current_date", "n and not spoiled = true", "cast(n as text)", "exists (select n from arrived)", "n; n", "n & 1",
            "limit 1", "fetch first row only", "shop collate nocase", "interval '1' day", "extract(day from n)", "count(*)", "sum(n)", "n between 1 and 2 or n = 3", "#", "n -> 2", "n ~ 2", "!n", "\\",
        ):
            with self.subTest(what):
                self.assertTrue(not_plain(f"{statement('lines.sql')}\n{what}\n"))
        self.assertEqual(not_plain(f"{statement('lines.sql')}\n where n between 1 and 2 and shop is not null and n <> 2 and shop in ('north')\n"), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
