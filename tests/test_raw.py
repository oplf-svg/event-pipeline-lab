"""The files: written once, and if something that a list names is changed, cut, taken away or exchanged, it shows in the next run."""

import base64
import hashlib
import importlib.metadata
import json
import os
import pathlib
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
import unittest.mock

from lab import LIMITS, NOW_US, ROOT, SHOPS, Lab, engine, feed, run

from pipeline import store

STORES = [store.Plain] + ([store.Parquet] if len(engine.all_of_them()) > 1 else [])


class Files(Lab):
    def setUp(self):
        self.place = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))

    def pipeline(self, name="pipeline", store_of=store.Plain):
        return run.Pipeline(self.place / name, SHOPS, LIMITS, store_of=store_of)

    @staticmethod
    def raw(pipeline, at):
        return sorted((pipeline.folder / "raw").glob("[0-9]*"))[at]

    @staticmethod
    def last_list(pipeline, change):
        """Changes the last list, which nobody has listed yet."""
        path = max((pipeline.folder / "runs").iterdir())
        said = json.loads(path.read_text())
        change(said)
        path.unlink()
        path.write_text(json.dumps(said, indent=1, sort_keys=True) + "\n")

    def two_runs(self, store_of=store.Plain):
        """Two runs, each with two batches of new lines."""
        story, one = feed.Story(), self.pipeline(store_of=store_of)
        for day in ("2027-03-10", "2027-03-11"):
            for _ in range(2):
                one.take([story.order(shop, f"{day}T12:00:00").line for shop in SHOPS for _ in range(2)])
            self.assertEqual(one.run(story.closing()).problems, [])
        return story, one

    def test_what_is_kept_is_what_arrived(self):
        nasty = [b"", b"\n", b"\r\n", bytes(range(256)), b"\xff" * 1000, feed.Story().order().line]
        for store_of in STORES:
            with self.subTest(store_of.name):
                self.assertEqual(store_of.lines(store_of.of_lines(nasty)), nasty)
                self.assertEqual(store_of.lines(store_of.of_lines([])), [])
                texts = ["", " ", "x\ny", "x\r\ny", "\n", 'say "x"', '"', "a,b", ",", "\\", "\\N", "ä", "NULL", "null", "0x10", "1e3", "' or 1=1 --", "x " * 50_000]
                rows = [[place, None if place % 3 else 2**53 - place, text, None if place % 2 else text] for place, text in enumerate(texts, 1)]
                self.assertEqual(store_of.rows(store_of.of_rows([("a", "whole"), ("b", "whole"), ("c", "text"), ("d", "text")], rows)), rows)
                self.assertEqual(store_of.rows(store_of.of_rows([("a", "whole"), ("b", "text")], [])), [])

    def test_a_long_line_stops_nobody(self):
        """DuckDB refuses rows above 2 MB, if nobody tells it not to. Then all lines that came with it would be lost."""
        good = feed.Story().order().line
        for store_of in STORES:
            with self.subTest(store_of.name):
                one = self.pipeline(store_of.name, store_of)
                one.take([good, b"x" * 5_000_000, good])
                self.assertEqual([row.reason for row in one.run().rows], ["an order", "spoiled", "the same line"])
                # In the file that DuckDB reads each of these takes two bytes.
                rows = [[1, '"' * 1_500_000], [2, "x"]]
                self.assertEqual(store_of.rows(store_of.of_rows([("a", "whole"), ("b", "text")], rows)), rows)

    def test_a_folder_with_any_name(self):
        """Its name stands in a statement."""
        place = self.place / "it's 'here'"
        place.mkdir()
        real, tempfile.tempdir = tempfile.tempdir, str(place)
        try:
            for store_of in STORES:
                try:
                    lines = store_of.lines(store_of.of_lines([b"x"]))
                except Exception as problem:
                    raise self.failureException(f"it breaks with {type(problem).__name__}") from None
                self.assertEqual(lines, [b"x"])
        finally:
            tempfile.tempdir = real

    @unittest.skipUnless(len(STORES) > 1, "DuckDB is not here, and nothing else writes Parquet")
    def test_parquet_has_only_what_every_engine_means_the_same_by(self):
        path = self.place / "file.parquet"
        for data, wanted in (
            (store.Parquet.of_lines([b"x"]), [("place", "INT64", None, 1), ("line", "BYTE_ARRAY", None, 2)]),
            (store.Parquet.of_rows([("n", "whole"), ("shop", "text")], [[1, "north"]]), [("n", "INT64", None, 1), ("shop", "BYTE_ARRAY", "UTF8", 2)]),
        ):
            path.write_bytes(data)
            said = engine.Duck().ask(f"select name, type, converted_type, field_id from parquet_schema('{path}') where type is not null")
            self.assertEqual([(name, kind, None if meant in (None, "INT_64") else meant, number) for name, kind, meant, number in said], wanted)
            self.assertEqual(store.Parquet.rows(store.Parquet.of_lines([b"x", b"y"])), [[1, b"x"], [2, b"y"]])
            packed = engine.Duck().ask(f"select distinct compression from parquet_metadata('{path}')")
            self.assertEqual(packed, [("SNAPPY",)])

    @unittest.skipUnless(len(STORES) > 1, "DuckDB is not here")
    def test_duckdb_fetches_nothing_while_it_runs(self):
        for name in ("autoinstall_known_extensions", "autoload_known_extensions"):
            self.assertEqual(engine.Duck().ask(f"select current_setting('{name}')"), [(False,)])

    def test_a_file_is_written_once(self):
        path = self.place / "file.txt"
        store.put(path, b"first")
        for data in (b"second", b"first", b""):
            with self.assertRaises(FileExistsError):
                store.put(path, data)
        self.assertEqual(path.read_bytes(), b"first")
        self.assertEqual([found.name for found in self.place.iterdir()], ["file.txt"])

    def test_a_run_adds_up(self):
        for store_of in STORES:
            with self.subTest(store_of.name):
                story = feed.Story()
                one = self.pipeline(store_of.name, store_of)
                one.take([story.order(shop).line for shop in SHOPS])
                first = one.run()
                one.take([story.order("plaza").line, story.sent[0].line])
                second = one.run(story.closing())
                self.assertEqual([first.run, second.run], [1, 2])
                self.assertEqual([first.counts["all"]["raw"], second.counts["all"]["raw"]], [3, 5])
                self.assertEqual((second.counts["all"]["valid"], second.counts["all"]["duplicate"], second.problems), (4, 1, []))

    def test_the_same_again_says_the_same(self):
        story, one = self.two_runs()
        shutil.copytree(one.folder, self.place / "copy")
        there = self.pipeline("copy").run(story.closing())
        here = one.run(story.closing())
        self.assertEqual(here, there)
        self.assertEqual((one.folder / "runs" / "000003.json").read_bytes(), (self.place / "copy" / "runs" / "000003.json").read_bytes())

    def test_a_run_without_anything_new(self):
        story, one = self.two_runs()
        third = one.run(story.closing())
        self.assertEqual(([row.verdict for row in third.rows], third.counts["all"]["raw"]), (["valid"] * 24, 24))
        fourth = one.run(story.closing())
        self.assertEqual((third.rows, third.counts), (fourth.rows, fourth.counts))

    def test_nothing_has_arrived_yet(self):
        one = self.pipeline()
        at_us = feed.moment("north", "2027-03-10T12:00:00")
        self.assertEqual((one.run().rows, one.run({"at_us": at_us, "numbers": {}}).problems), ([], []))
        self.assertEqual(one.run({"at_us": at_us + 1, "numbers": {"north": 2}}).problems, ["north: 2 of 2 numbers are missing, the first is 1"])

    def test_a_list_says_what_a_run_did(self):
        story, one = self.two_runs()
        said = json.loads((one.folder / "runs" / "000002.json").read_text())
        self.assertEqual([file["file"] for file in said["raw"]], [self.raw(one, at).name for at in range(4)])
        self.assertEqual([file["lines"] for file in said["raw"]], [6, 6, 6, 6])
        self.assertEqual((said["shops"], said["limits"], said["closing"]), (SHOPS, LIMITS, story.closing()))
        self.assertEqual((said["counts"]["all"]["valid"], said["counts"]["reasons"]), (24, {"valid: an order": 24}))
        # What decides is named, with its fingerprint.
        for name in ("rules/lines.sql", "rules/valid.sql", "rules/marks.sql", "rules/verdicts.sql", "pipeline/run.py", "pipeline/reader.py", "pipeline/days.py"):
            self.assertEqual(said["program"][name], hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
        self.assertEqual((said["program"]["python"], said["program"]["sqlite"]), (platform.python_version(), sqlite3.sqlite_version))
        if len(STORES) > 1:
            self.assertEqual(said["program"]["duckdb"], importlib.metadata.version("duckdb"))
        with unittest.mock.patch("importlib.metadata.version", lambda name: {"tzdata": "2026.6"}[name]):
            self.assertEqual(run.clock(), "tzdata 2026.6")
        with unittest.mock.patch("importlib.metadata.version", side_effect=importlib.metadata.PackageNotFoundError):
            self.assertEqual(run.clock(), "the one of this machine")
        self.assertEqual(said["clock"], run.clock())
        story.unreadable("north", "not an object", b"[]")
        one.take([story.sent[-1].line, story.sent[0].line, b"spoiled"])
        self.assertEqual(one.run(story.closing()).counts["reasons"], {"bad: not an object": 1, "bad: spoiled": 1, "duplicate: the same line": 1, "valid: an order": 24})

    def test_the_verdicts_in_the_file_are_those_of_the_run(self):
        for store_of in STORES:
            with self.subTest(store_of.name):
                story, one = feed.everything(5, 120), self.pipeline(store_of.name, store_of)
                one.take([sent.line for sent in story.sent])
                done = one.run(story.closing())
                said = json.loads((one.folder / "runs" / "000001.json").read_text())
                path = one.folder / "verdicts" / said["verdicts"]["file"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), said["verdicts"]["sha256"])
                self.assertEqual([run.Verdict(*row) for row in store_of.rows(path.read_bytes())], done.rows)

    def test_the_engine_that_was_chosen_judges(self):
        asked = []

        class Asked(engine.Sqlite):
            def rule(self, name, text):
                asked.append(name)
                super().rule(name, text)

        one = run.Pipeline(self.place, SHOPS, LIMITS, Asked)
        one.take([feed.Story().order().line])
        one.run()
        self.assertEqual(asked, list(run.RULES))

    def test_settings_that_cannot_be(self):
        for what, shops, limits in (
            ("a clock that is not there", {"north": [["2027-03-20", "Europe/Pariss"]]}, {}),
            ("a date that is written in another way", {"north": [["2027-2-10", "Europe/London"]]}, {}),
            ("a date that is none", {"north": [["2027-02-30", "Europe/London"]]}, {}),
            ("a date without its lines", {"north": [["20270210", "Europe/London"]]}, {}), ("a date by its week", {"north": [["2027-W06-3", "Europe/London"]]}, {}),
            ("no clock at all", {"north": []}, {}),
            ("two clocks from one day on", {"north": [["2027-02-10", "Europe/London"], ["2027-02-10", "Europe/Madrid"]]}, {}),
            ("a date that no line can have", {"north": [["1999-12-31", "Europe/London"]]}, {}), ("a date before 1970", {"north": [["1969-12-30", "Europe/London"]]}, {}),
            ("a date that nobody will see", {"north": [["2200-01-01", "Europe/London"]]}, {}),
            ("a move to where the day before has not begun", {"north": [["2026-01-01", "Pacific/Pago_Pago"], ["2027-02-10", "Pacific/Kiritimati"]]}, {}),
            ("a move on which two days begin at the same moment", {"north": [["2026-01-01", "Pacific/Pago_Pago"], ["2027-04-04", "Pacific/Auckland"]]}, {}),
            ("a move on which a day is closed before the one before it", {"north": [["2026-01-01", "Pacific/Pago_Pago"], ["2027-09-26", "Pacific/Chatham"]]}, {}),
            ("a shop in large letters", {"North": [["2027-02-10", "Europe/London"]]}, {}),
            ("an hour that is none", SHOPS, {"closes_at": "25:00"}), ("an hour without minutes", SHOPS, {"closes_at": "06"}), ("with seconds", SHOPS, {"closes_at": "06:00:01"}),
            ("days as a text", SHOPS, {"oldest_days": "35"}), ("a part of a day", SHOPS, {"oldest_days": 0.5}), ("less than no day", SHOPS, {"oldest_days": -1}),
            ("true minutes", SHOPS, {"future_minutes": True}), ("a day more than a hundred years", SHOPS, {"oldest_days": 36_501}),
            ("a minute more than a year", SHOPS, {"future_minutes": 525_601}), ("more minutes than an engine can count", SHOPS, {"future_minutes": 153_722_867_280}),
        ):
            with self.subTest(what), self.assertRaises(ValueError):
                run.Pipeline(self.place, shops, LIMITS | limits)
        for name in ("oldest_days", "future_minutes", "closes_at"):
            with self.subTest(f"without {name}"), self.assertRaises(KeyError):
                run.Pipeline(self.place, SHOPS, {key: value for key, value in LIMITS.items() if key != name})
        for shops in ({}, {"old": [["2000-01-01", "Europe/London"]]}, {"new": [["2199-12-31", "Europe/London"]]}, {"mover": [["2026-01-01", "Pacific/Apia"], ["2027-02-10", "Pacific/Pago_Pago"]]}, {"mover": [["2027-02-10", "Europe/London"], ["2026-01-01", "America/New_York"]]}):
            run.Pipeline(self.place, shops, LIMITS | {"oldest_days": 0, "future_minutes": 0, "closes_at": "00:00"})

    def test_the_largest_limits(self):
        """Every engine can count with them."""
        for engine_of in engine.all_of_them():
            one = run.Pipeline(self.place / engine_of.name, SHOPS, LIMITS | {"oldest_days": 36_500, "future_minutes": 525_600}, engine_of)
            one.take([feed.Story().order().line])
            self.assertEqual([row.verdict for row in one.run().rows], ["valid"])

    def test_settings_in_which_a_name_stands_twice(self):
        real, run.ROOT = run.ROOT, self.place
        try:
            (self.place / "rules").mkdir()
            (self.place / "rules" / "limits.json").write_text("{}")
            (self.place / "shops.json").write_text('{"north": [], "north": []}')
            with self.assertRaises(ValueError):
                run.settings()
        finally:
            run.ROOT = real

    def test_18_any_change_of_a_listed_file_is_red(self):
        def flipped(data):
            return data[: len(data) // 2] + bytes([data[len(data) // 2] ^ 1]) + data[len(data) // 2 + 1 :]

        for kind, names in {"raw": [0, 3], "verdicts": [0, 1], "runs": [0, 1]}.items():
            for name in names:
                for what, change in {
                    "a bit": flipped, "cut": lambda data: data[: len(data) // 2], "a line less": lambda data: b"".join(data.splitlines(keepends=True)[:-1]),
                    "a line twice": lambda data: data + data.splitlines(keepends=True)[-1], "empty": lambda data: b"", "gone": lambda data: None,
                }.items():
                    with self.subTest(f"{kind} {name}: {what}"):
                        self.setUp()
                        story, one = self.two_runs()
                        path = sorted((one.folder / kind).iterdir())[name]
                        changed = change(path.read_bytes())
                        path.unlink()
                        if changed is not None:
                            path.write_bytes(changed)
                        before = {found: found.read_bytes() for found in one.folder.rglob("*") if found.is_file()}
                        if (kind, name, what) == ("runs", 1, "gone"):
                            # What nobody has listed yet can be taken away. Whoever counts the runs from outside sees it.
                            self.assertEqual(one.run(story.closing()).run, 2)
                            continue
                        with self.assertRaises(run.Red):
                            one.run(story.closing())
                        self.assertEqual(before, {found: found.read_bytes() for found in one.folder.rglob("*") if found.is_file()}, "something was written")

    def test_18_verdicts_that_add_up_and_are_wrong_are_red(self):
        """Two lines have changed their days. All sums are as before."""
        story, one = feed.Story(), self.pipeline()
        one.take([story.order(placed="2027-03-10T12:00:00").line, story.order(placed="2027-03-11T12:00:00").line])
        one.run()
        path = next((one.folder / "verdicts").iterdir())
        data = path.read_bytes()
        path.unlink()
        path.write_bytes(data.replace(b"2027-03-10", b"x").replace(b"2027-03-11", b"2027-03-10").replace(b"x", b"2027-03-11"))
        self.assertNotEqual(path.read_bytes(), data)
        with self.assertRaises(run.Red):
            one.run(story.closing())

    def test_18_the_witness_sees_what_nobody_else_can(self):
        for what in ("gone", "changed", "another one"):
            with self.subTest(what):
                self.setUp()
                story, one = self.two_runs()
                last = one.run(story.closing())
                self.assertEqual(one.run(story.closing(), last.witness).problems, [])
                (one.folder / "runs" / "000004.json").unlink()
                path = one.folder / "runs" / "000003.json"
                data = path.read_text()
                path.unlink()
                if what == "changed":
                    path.write_text(data.replace('"clock": "', '"clock": "not '))
                if what == "another one":
                    one.run({"at_us": feed.moment("north", "2027-03-10T12:00:00"), "numbers": {}})
                with self.assertRaises(run.Red):
                    one.run(story.closing(), last.witness)
        with self.assertRaises(run.Red):
            self.pipeline("fresh").run(witness=last.witness)
        # Whoever says that there was no run yet is heard as well.
        self.assertEqual(self.pipeline("fresh").run(witness="").run, 1)
        with self.assertRaises(run.Red):
            one.run(story.closing(), "")

    def test_18_every_word_of_an_older_list_counts(self):
        """Its fingerprint stands in the list after it, so whoever has seen that one vouches for it as well."""
        story, one = self.two_runs()
        witness = hashlib.sha256((one.folder / "runs" / "000002.json").read_bytes()).hexdigest()
        path = one.folder / "runs" / "000001.json"
        data = path.read_text()
        path.unlink()
        path.write_text(data.replace('"clock": "', '"clock": "not '))
        for seen in (witness, None):
            with self.subTest(seen=seen), self.assertRaises(run.Red):
                one.run(story.closing(), seen)

    def test_18_a_list_under_another_name_is_red(self):
        """The next one would take its place."""
        story, one = self.two_runs()
        last = one.folder / "runs" / "000002.json"
        last.rename(last.with_name("000009.json"))
        with self.assertRaises(run.Red):
            one.run(story.closing())

    def test_18_lists_that_lose_a_file_are_red(self):
        """The last list is true in itself, but it knows fewer files than the one before it."""
        story, one = self.two_runs()
        less = self.pipeline("less")
        (less.folder / "raw").mkdir(parents=True)
        shutil.copy(self.raw(one, 0), less.folder / "raw")
        less.run()
        of_it = json.loads((less.folder / "runs" / "000001.json").read_text())
        # Under the name that the second run would give it, and for what comes afterwards under its own.
        name = "000002" + of_it["verdicts"]["file"][6:]
        for there in (name, of_it["verdicts"]["file"]):
            shutil.copy(less.folder / "verdicts" / of_it["verdicts"]["file"], one.folder / "verdicts" / there)
        came = list(run.arrived(store.Plain.lines(self.raw(one, 0).read_bytes())))
        made, *_ = one._made(one._past()[:1], of_it["raw"], came, SHOPS, LIMITS, None)
        path = one.folder / "runs" / "000002.json"
        path.unlink()
        path.write_bytes(run._written(made | {"verdicts": of_it["verdicts"] | {"file": name}}))
        with self.assertRaisesRegex(run.Red, "does not follow the run before it"):
            one.run(story.closing())
        # It is red because of the files, and not because it was not written by the program: alone it is fine.
        (one.folder / "runs" / "000001.json").unlink()
        path.unlink()
        made, *_ = one._made([], of_it["raw"], came, SHOPS, LIMITS, None)
        (one.folder / "runs" / "000001.json").write_bytes(run._written(made | {"verdicts": of_it["verdicts"]}))
        self.assertEqual(one.run(story.closing()).run, 2)

    def test_21_whoever_dies_while_writing_leaves_no_file(self):
        real, written = os.fsync, []

        def dies(file):
            written.append(os.fstat(file).st_size)
            raise KeyboardInterrupt

        os.fsync = dies
        try:
            with self.assertRaises(KeyboardInterrupt):
                store.put(self.place / "file.txt", b"all of it")
        finally:
            os.fsync = real
        self.assertEqual((list(self.place.iterdir()), written), ([], [9]))

    def test_21_what_was_kept_survives_a_power_failure(self):
        """As far as it is asked for: each folder that was not there, the file, and then its name in its folder."""
        real, asked = os.fsync, []

        def fsync(place):
            everything = [self.place, *self.place.rglob("*")]
            (which,) = (found.relative_to(self.place) for found in everything if os.path.samestat(os.stat(found), os.fstat(place)))
            asked.append(("a file" if stat.S_ISREG(os.fstat(place).st_mode) else str(which), [found.name for found in everything if found.is_file() and found.name in "12"]))
            real(place)

        with unittest.mock.patch.object(os, "fsync", fsync):
            store.put(self.place / "new" / "raw" / "1", b"first")
            store.put(self.place / "new" / "raw" / "2", b"second")
        self.assertEqual(asked[:4], [(".", []), ("new", []), ("a file", []), ("new/raw", ["1"])])
        self.assertEqual([(what, sorted(there)) for what, there in asked[4:]], [("a file", ["1"]), ("new/raw", ["1", "2"])])

    def test_18_two_files_that_changed_places_are_red(self):
        story, one = self.two_runs()
        first, second = self.raw(one, 0), self.raw(one, 1)
        data = first.read_bytes(), second.read_bytes()
        for path, other in ((first, data[1]), (second, data[0])):
            path.unlink()
            path.write_bytes(other)
        with self.assertRaises(run.Red):
            one.run(story.closing())

    def test_18_two_files_that_changed_their_names_are_red(self):
        """Their contents fit their names. But the places of their lines are others than those that were listed."""
        story, one = self.two_runs()
        first, second = self.raw(one, 0), self.raw(one, 1)
        first.rename(first.with_name("000002" + first.name[6:]))
        second.rename(second.with_name("000001" + second.name[6:]))
        with self.assertRaises(run.Red):
            one.run(story.closing())

    def test_18_what_happens_to_a_file_before_it_is_listed_is_red(self):
        for store_of in STORES:
            for what, change in {
                "cut by ten bytes": lambda data: data[:-10], "a bit": lambda data: data[:-30] + bytes([data[-30] ^ 1]) + data[-29:], "empty": lambda data: b"",
                "twice": lambda data: data + data, "a line less": lambda data: b"".join(data.splitlines(keepends=True)[:-1]), "something else": lambda data: b"whatever\n",
            }.items():
                with self.subTest(what, store=store_of.name):
                    self.setUp()
                    story, one = feed.Story(), self.pipeline(store_of=store_of)
                    one.take([story.order().line for _ in range(4)])
                    path = self.raw(one, 0)
                    data = path.read_bytes()
                    path.unlink()
                    path.write_bytes(change(data))
                    with self.assertRaises(run.Red):
                        one.run(story.closing())

    def test_18_a_file_that_nobody_took_is_red(self):
        nothing = hashlib.sha256(b"").hexdigest()[:16]
        for name in ("000005.txt", f"000005-{nothing}.parquet", f"5-{nothing}.txt", f"000005-{nothing}.txt.old", f"x000005-{nothing}.txt", "zzz", f"000005-{'0' * 16}.txt"):
            with self.subTest(name):
                self.setUp()
                story, one = self.two_runs()
                (one.folder / "raw" / name).write_bytes(b"")
                with self.assertRaises(run.Red):
                    one.run(story.closing())
        # What it says of them may stand in a public log.
        for kind, name in (("raw", "000005\n::error::x"), ("runs", "000003\n::error::x")):
            self.setUp()
            story, one = self.two_runs()
            (one.folder / kind / name).write_bytes(b"")
            with self.assertRaises(run.Red) as red:
                one.run(story.closing())
            self.assertIn("\\n::error::x", str(red.exception))
            self.assertNotIn("\n", str(red.exception))
        self.setUp()
        story, one = self.two_runs()
        (one.folder / "raw" / f"000005-{nothing}.txt").mkdir()
        with self.assertRaises(run.Red):
            one.run(story.closing())

    def test_18_verdicts_of_another_form_are_red(self):
        """A version of the program that has written other columns. Its list has a witness, so only the form is in the way."""
        story, one = self.two_runs()
        data = store.Plain.of_rows([*run.VERDICTS, ("more_of_it", "whole")], [[*row, 1] for row in one._verdicts(one._past()[-1][1])])
        fingerprint = hashlib.sha256(data).hexdigest()
        (one.folder / "verdicts" / f"000002-{fingerprint[:16]}.txt").write_bytes(data)
        self.last_list(one, lambda said: said.update(program={}, verdicts={"file": f"000002-{fingerprint[:16]}.txt", "sha256": fingerprint}))
        with self.assertRaisesRegex(run.Red, "the verdicts of run 2 have another form"):
            one.run(story.closing(), hashlib.sha256((one.folder / "runs" / "000002.json").read_bytes()).hexdigest())

    def test_18_verdicts_under_another_name_are_red(self):
        """They are the same verdicts, and the list says where they lie. But no run has put them there."""
        for place in ("../outside.txt", "other.txt", "000001-{}.txt", "000002-{}.txt.old", "000002-{}-.txt", "x000002-{}.txt", "000002-{}x.txt"):
            with self.subTest(place):
                self.setUp()
                story, one = self.two_runs()
                said = json.loads((one.folder / "runs" / "000002.json").read_text())["verdicts"]
                name = place.format(said["sha256"][:16])
                (one.folder / "verdicts" / said["file"]).rename(one.folder / "verdicts" / name)
                self.last_list(one, lambda said, name=name: said["verdicts"].update(file=name))
                with self.assertRaisesRegex(run.Red, "the verdicts of run 2 were changed"):
                    one.run(story.closing())

    def test_18_a_folder_that_cannot_be_read_is_red(self):
        """It is not an empty one, and whoever keeps something there comes to an end."""
        for kind in ("raw", "runs"):
            for what, put in (("a file", lambda place: place.write_text("no folder")), ("a link that leads nowhere", lambda place: place.symlink_to(place.parent.parent / "nowhere"))):
                with self.subTest(what, kind=kind):
                    self.setUp()
                    one = self.pipeline()
                    one.folder.mkdir()
                    put(one.folder / kind)
                    with self.assertRaisesRegex(run.Red, f"{kind} cannot be read"):
                        one.run()
        gone = self.pipeline("gone")
        gone.folder.symlink_to(self.place / "nowhere")
        tries, real = [], store.put

        def put(path, data):
            tries.append(path)
            self.assertLess(len(tries), 5, "it never ends")
            real(path, data)

        with unittest.mock.patch.object(store, "put", put), self.assertRaises(NotADirectoryError):
            gone.take([b"x"])

    def test_a_closing_that_is_none(self):
        one = self.pipeline()
        first, last = feed.micros("2000-01-01T00:00:00"), feed.micros("2199-12-31T23:59:59.999999")
        for at_us in ("1", -1, 0, 1, True, 1.5 * first, None, first - 1, last + 1, 10**30):
            with self.subTest(at_us=at_us), self.assertRaises(ValueError):
                one.run({"at_us": at_us, "numbers": {}})
        for numbers in ({"north": "4"}, {"north": -1}, {"north": None}, {"north": True}, {"north": 4.0}, {"north": 2**53}, {"North": 4}, {"": 4}):
            with self.subTest(numbers=numbers), self.assertRaises(ValueError):
                one.run({"at_us": first, "numbers": numbers})
        for at_us in (first, last):
            self.assertEqual(one.run({"at_us": at_us, "numbers": {"north": 0}}).problems, [])

    def test_18_a_file_that_cannot_be_read_is_red(self):
        """Its name fits, so whoever took it did it in another way."""
        for store_of in STORES:
            for data in (b"not base64!\n", b"AAAA", b"\xff\xff\n", b"AA=A\n", b"PAR1PAR1"):
                with self.subTest(store=store_of.name, data=data):
                    self.setUp()
                    one = self.pipeline(store_of=store_of)
                    one.take([])
                    (one.folder / "raw" / f"000002-{hashlib.sha256(data).hexdigest()[:16]}{store_of.ending}").write_bytes(data)
                    with self.assertRaises(run.Red):
                        one.run()

    def test_26_a_closing_that_takes_something_back_is_red(self):
        story, one = feed.Story(), self.pipeline()
        one.take([story.order().line for _ in range(4)])
        first = story.closing()
        self.assertEqual(one.run(first).problems, [])
        # A run without a closing does not make it forgotten.
        one.run()
        one.take([story.order(placed="2027-03-11T12:00:00").line])
        for what, closing, said in (
            ("fewer numbers", {"at_us": first["at_us"] + 1, "numbers": {"north": 3}}, "north: 3 are announced, and 4 were in the closing before"),
            ("no shop", {"at_us": first["at_us"] + 1, "numbers": {}}, "north: 0 are announced, and 4 were in the closing before"),
            ("other numbers at the same moment", {"at_us": first["at_us"], "numbers": {"north": 5}}, "north: 5 are announced, and 4 were in the closing before"),
            ("an earlier moment", {"at_us": first["at_us"] - 1, "numbers": {"north": 4}}, "the closing before was asked at a later moment"),
        ):
            with self.subTest(what):
                again = run.Pipeline(shutil.copytree(one.folder, self.place / what), SHOPS, LIMITS)
                for _ in range(2):
                    self.assertIn(said, again.run(closing).problems)
        # Nobody has to keep to a closing that was wrong itself.
        self.assertEqual(one.run(story.closing() | {"numbers": {"north": 99}}).problems, ["north: 94 of 99 numbers are missing, the first is 6"])
        self.assertEqual(one.run(first).problems, [])
        self.assertEqual(one.run(story.closing()).problems, [])

    def test_25_other_settings_do_not_change_what_was_said(self):
        for what, shops, limits, changed, place in (
            # Without the second order, the third one is not out of order any more.
            ("a younger limit", {}, {"oldest_days": 10}, 1, 1), ("less of a future", {}, {"future_minutes": 1}, 2, 2), ("another hour", {}, {"closes_at": "20:00"}, 1, 3),
            ("another clock", {"north": [["2026-01-01", "America/New_York"]]}, {}, 1, 3), ("a shop more", {"island": [["2026-01-01", "Europe/Madrid"]]}, {}, 0, 0), ("nothing", {}, {}, 0, 0),
        ):
            with self.subTest(what):
                self.setUp()
                story, one = feed.Story(), self.pipeline()
                one.take([
                    story.order(placed="2027-02-10T12:00:00", received="2027-03-10T12:00:00", late=1).line, story.order(placed="2027-03-10T12:03:00", received="2027-03-10T12:00:00").line,
                    story.order(placed="2027-03-10T03:00:00", received="2027-03-11T12:00:00", late=1).line,
                ])
                self.assertEqual(one.run().problems, [])
                one.shops, one.limits = SHOPS | shops, LIMITS | limits
                # To be red once does not make it right.
                for _ in range(2):
                    self.assertEqual(one.run().problems, [f"{changed} verdicts are not what they were, the first is at place {place}"] if changed else [])
                one.shops, one.limits = SHOPS, LIMITS
                self.assertEqual(one.run().problems, [])

    def test_25_another_rule_does_not_change_what_was_said(self):
        story, one = feed.Story(), self.pipeline()
        one.take([story.order().line, story.order(received="2027-03-11T06:00:00", late=1).line])
        first = one.run()
        other = self.place / "other"
        for part in ("rules", "pipeline"):
            shutil.copytree(ROOT / part, other / part)
        path = other / "rules" / "marks.sql"
        path.write_text(path.read_text().replace("a.received_us >= v.closes_us", "a.received_us > v.closes_us"))
        with unittest.mock.patch.object(run, "ROOT", other):
            second = one.run(witness=first.witness)
            # To be red once does not make it right.
            third = one.run(witness=second.witness)
        self.assertEqual([(done.problems, [row.late for row in done.rows]) for done in (first, second, third)], [([], [0, 1]), *[(["1 verdicts are not what they were, the first is at place 2"], [0, 0])] * 2])
        self.assertEqual(one.run(witness=third.witness).problems, [])

    def test_13_a_shop_gets_its_clock_later(self):
        """What was said of its orders before has no say, because the runs were red."""
        story, one = feed.Story(), self.pipeline()
        one.take([story.order().line, story.order("plaza").line])
        one.shops = {"north": SHOPS["north"]}
        for _ in range(2):
            done = one.run()
            self.assertEqual(([row.verdict for row in done.rows], done.problems), (["valid", "bad"], ["plaza has no clock"]))
        one.shops = SHOPS
        done = one.run(story.closing())
        self.assertEqual(([row.verdict for row in done.rows], done.problems), (["valid", "valid"], []))

    def test_26_a_closing_that_was_asked_too_early_is_red(self):
        """Something was received before its moment and got its number afterwards. So what was said then was not all."""
        story, one = feed.Story(), self.pipeline()
        one.take([story.order(placed="2027-03-10T12:00:00").line])
        first = {"at_us": feed.moment("north", "2027-03-12T07:00:00"), "numbers": {"north": 1}}
        self.assertEqual(one.run(first).problems, [])
        one.take([story.order(placed="2027-03-10T13:00:00", received="2027-03-11T07:00:00", late=1).line])
        said = ["north: 1 numbers above the announced 1 were received before the closing before"]
        # At the next closing, at the same one, and without any.
        for closing in (story.closing(feed.moment("north", "2027-03-13T07:00:00")), None, first | {"numbers": {"north": 2}}):
            self.assertIn(said[0], one.run(closing).problems)
        # What was received at its moment or later is another matter.
        story, one = feed.Story(), self.pipeline("other")
        one.take([story.order(placed="2027-03-10T12:00:00").line])
        self.assertEqual(one.run(first).problems, [])
        one.take([story.order(placed="2027-03-10T13:00:00", received="2027-03-12T07:00:00", late=1).line])
        self.assertEqual(one.run(story.closing(feed.moment("north", "2027-03-13T07:00:00"))).problems, [])

    def test_26_a_closing_in_the_last_list_that_nobody_could_ask_is_red(self):
        """It is what comes out once more, so whoever can write files can put it there."""
        ahead = 3_600_000_000
        for what, change in (
            ("its moment has not come", lambda closing: closing.update(at_us=closing["at_us"] + ahead)), ("it is no moment", lambda closing: closing.update(at_us=1.5e15)),
            ("a number that is none", lambda closing: closing["numbers"].update(north=True)), ("a shop that cannot be", lambda closing: closing["numbers"].update({"North!": 1})),
        ):
            with self.subTest(what):
                self.setUp()
                story, one = self.two_runs()
                closing, witness = story.closing(), hashlib.sha256((one.folder / "runs" / "000002.json").read_bytes()).hexdigest()
                change(closing)
                with unittest.mock.patch.object(run, "check_closing"):
                    one.run(closing, witness)
                with unittest.mock.patch.object(run, "now_us", lambda story=story: story.closing()["at_us"]), self.assertRaisesRegex(run.Red, "the last list has a closing that is none, or whose moment has not come"):
                    one.run(story.closing(), witness)

    def test_26_a_closing_whose_moment_has_not_come(self):
        """By the clock of this machine, and the one that answered may be five minutes ahead."""
        at_us = feed.moment("north", "2027-03-12T07:00:00")
        with unittest.mock.patch.object(run, "now_us", lambda: at_us):
            for ahead in (300_000_000, 300_000_001, 3_600_000_000):
                with self.subTest(ahead=ahead), self.assertRaises(ValueError):
                    self.pipeline(f"ahead {ahead}").run({"at_us": at_us + ahead, "numbers": {}})
            for ahead in (299_999_999, 1, 0, -3_600_000_000):
                self.assertEqual(self.pipeline(f"ahead {ahead}").run({"at_us": at_us + ahead, "numbers": {}}).problems, [])
        self.assertLess(abs(NOW_US() - int(time.time() * 1_000_000)), 60_000_000)

    def test_07_what_waits_may_change_and_nothing_else(self):
        story, one = feed.Story(), self.pipeline()
        lines = [story.order().line for _ in range(4)]
        one.take([lines[0], lines[2], lines[2], lines[3]])
        self.assertEqual([row.verdict for row in one.run().rows], ["valid", "waiting", "duplicate", "waiting"])
        one.take([lines[1]])
        done = one.run(story.closing())
        self.assertEqual(([row.verdict for row in done.rows], done.problems), (["valid", "valid", "duplicate", "valid", "valid"], []))

    def test_18_a_list_that_says_more_than_its_verdicts_is_red(self):
        for change in (
            lambda said: said["counts"]["all"].update(valid=25), lambda said: said.update(problems=["x"]), lambda said: said["closing"]["numbers"].update(north=99),
            lambda said: said["raw"][3].update(lines=7), lambda said: said.update(run=7), lambda said: said.update(counts=None), lambda said: said.update(closing=3), lambda said: said.pop("program"),
            lambda said: said["limits"].update(oldest_days=-1), lambda said: said["limits"].update(future_minutes=None), lambda said: said["shops"].pop("plaza"), lambda said: said.update(shops={"north": [["2027-01-01", "Nowhere"]]}),
            lambda said: said["verdicts"].update(file="../runs/000001.json"), lambda said: said.update(more=1), lambda said: said.update(clock="x"),
            lambda said: said["raw"].append(said["raw"][0]), lambda said: said["raw"][0].pop("file"), lambda said: said["raw"][0].update(lines=-1), lambda said: said["raw"][0].update(more=1),
            lambda said: said.update(raw=[1]), lambda said: said.update(raw="x"), lambda said: said.update(raw=None),
        ):
            self.setUp()
            story, one = self.two_runs()
            self.last_list(one, change)
            with self.assertRaises(run.Red):
                one.run(story.closing())

    def test_18_a_list_that_is_nothing_is_red(self):
        story, one = self.two_runs()
        for data in (b"", b"{}", b"[]", b"null", b"[" * 200_000, b'{"run": 2}', b"\xff"):
            path = one.folder / "runs" / "000002.json"
            path.unlink()
            path.write_bytes(data)
            with self.subTest(data=data[:20]), self.assertRaises(run.Red):
                one.run(story.closing())
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(run.Red, "cannot be read, or its verdicts are gone"):
            one.run(story.closing())

    def test_18_the_last_list_written_in_another_way_is_red(self):
        """It says the same, in other bytes. Nobody but the program writes lists."""
        story, one = self.two_runs()
        path = one.folder / "runs" / "000002.json"
        said = json.loads(path.read_text())
        path.unlink()
        path.write_text(json.dumps(said))
        with self.assertRaises(run.Red):
            one.run(story.closing())
        # If somebody has seen exactly this one, it is theirs to say.
        self.assertEqual(one.run(story.closing(), hashlib.sha256(path.read_bytes()).hexdigest()).run, 3)

    def test_18_a_list_of_another_version_needs_its_witness(self):
        """Only the program that wrote a list can say whether it fits. After a new version somebody has to have seen it."""
        story, one = self.two_runs()
        for what, change in (("clock rules", lambda said: said.update(clock="tzdata 2026.5")), ("program", lambda said: said.update(program=said["program"] | {"pipeline/run.py": "0" * 64}))):
            # It counted in another way.
            self.last_list(one, lambda said, change=change: change(said) or said.update(counts={"all": {"lines": 24}}))
            path = max((one.folder / "runs").iterdir())
            with self.subTest(what):
                with self.assertRaisesRegex(run.Red, "another version of the program or with other clock rules"):
                    one.run(story.closing())
                done = one.run(story.closing(), hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual((done.run, done.problems), (int(path.stem) + 1, []))
                self.assertEqual(one.run(story.closing()).problems, [])

    def test_18_a_list_of_settings_that_cannot_be_is_red(self):
        """It is what comes out once more, but of settings that no run would take."""
        story, one = self.two_runs()
        one.limits = LIMITS | {"oldest_days": 35.0}
        self.assertEqual(one.run(story.closing()).problems, [])
        one.limits = LIMITS
        with self.assertRaisesRegex(run.Red, "the last list cannot be worked out once more: ValueError"):
            one.run(story.closing())

    def test_18_why_the_last_list_cannot_be_worked_out_is_said(self):
        """That there was no memory says nothing about the list. Which kind of problem it was is said, and not its words: they may be private."""
        story, one = self.two_runs()
        with unittest.mock.patch.object(run, "judge", side_effect=MemoryError("no place for N-1042")), self.assertRaises(run.Red) as red:
            one.run(story.closing())
        self.assertEqual(str(red.exception), "the last list cannot be worked out once more: MemoryError")
        self.assertNotIn("N-1042", "".join(traceback.format_exception(red.exception)))

    def test_21_what_a_run_left_that_died_is_in_nobodys_way(self):
        story, one = self.two_runs()
        # It died while a file was written, and after its verdicts were.
        (one.folder / "raw" / ".000005-0123456789abcdef.txt.0123456789abcdef").write_bytes(b"half of")
        (one.folder / "verdicts" / "000003-0123456789abcdef.txt").write_bytes(b"whatever")
        (one.folder / "runs" / ".000003.json").write_bytes(b"half of")
        one.take([story.order(placed="2027-03-12T12:00:00").line])
        self.assertEqual((one.run(story.closing()).problems, one.run(story.closing()).counts["all"]["valid"]), ([], 25))

    def test_21_a_run_that_dies_after_its_verdicts_is_simply_done_again(self):
        story, one = self.two_runs()
        put = store.put

        def dies(path, data):
            put(path, data)
            if path.parent.name == "verdicts":
                raise KeyboardInterrupt

        store.put = dies
        try:
            with self.assertRaises(KeyboardInterrupt):
                one.run(story.closing())
        finally:
            store.put = put
        # What it left may even have been changed since.
        left = max((one.folder / "verdicts").iterdir())
        for change in (lambda data: data, lambda data: data[:-1], lambda data: b""):
            data = left.read_bytes()
            left.unlink()
            left.write_bytes(change(data))
            again = run.Pipeline(shutil.copytree(one.folder, self.place / f"copy {len(list(self.place.iterdir()))}"), SHOPS, LIMITS)
            self.assertEqual((again.run(story.closing()).run, again.run(story.closing()).problems), (3, []))

    def test_21_a_run_that_dies_before_anybody_has_its_witness(self):
        story, one = self.two_runs()
        third = one.run(story.closing())
        # Of the fourth nobody has heard. Of two nobody may be unheard of.
        one.run(story.closing())
        fifth = one.run(story.closing(), third.witness)
        self.assertEqual((fifth.run, fifth.problems), (5, []))
        with self.assertRaises(run.Red):
            one.run(story.closing(), third.witness)
        self.assertEqual(one.run(story.closing(), fifth.witness).run, 6)

    def test_21_two_who_take_at_the_same_moment_are_both_kept(self):
        story, one = self.two_runs()
        files, (first, second) = one._files, [story.order(shop, "2027-03-12T12:00:00").line for shop in ("north", "plaza")]
        there = files("raw")
        # All of them look before anybody else has taken something.
        one._files = lambda kind: there
        for lines in ([first], [second], [first], [second], []):
            one.take(lines)
        one._files = files
        done = one.run(story.closing())
        self.assertEqual((done.problems, done.counts["all"]["duplicate"], len(files("raw"))), ([], 2, 9))

    def test_21_two_runs_at_the_same_moment(self):
        for kind in ("runs", "verdicts"):
            self.setUp()
            story, one = self.two_runs()
            other, put, done = self.pipeline(), store.put, []

            def other_is_faster(path, data, kind=kind, other=other, put=put, done=done, story=story):
                if path.parent.name == kind and not done:
                    done.append(other)
                    other.run(story.closing())
                put(path, data)

            store.put = other_is_faster
            try:
                with self.subTest(kind), self.assertRaises(run.Red):
                    one.run(story.closing())
            finally:
                store.put = put
            self.assertEqual(one.run(story.closing()).run, 4)

    def test_21_killed_at_any_moment(self):
        """A real process is killed in the middle of each of its writes, with half of it on the disk. What is in the folder is whole
        afterwards, and the next run simply does it."""
        program = (
            "import base64, os, stat, sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from pipeline import run\n"
            "real, left = os.fsync, [int(sys.argv[3])]\n"
            "def fsync(file):\n"
            "    real(file)\n"
            "    left[0] -= stat.S_ISREG(os.fstat(file).st_mode)\n"
            "    if not left[0] and stat.S_ISREG(os.fstat(file).st_mode):\n"
            "        os.ftruncate(file, os.fstat(file).st_size // 2)\n"
            "        print('half', flush=True)\n"
            "        time.sleep(60)\n"
            "os.fsync = fsync\n"
            "one = run.Pipeline(sys.argv[2], *run.settings())\n"
            "one.take([base64.b64decode(line) for line in sys.argv[4:]])\n"
            "one.run()\n"
        )
        # It writes the lines, the verdicts and the list.
        for write in (1, 2, 3):
            story, folder = feed.Story(), self.place / f"killed {write}"
            lines = [story.order(shop).line for shop in SHOPS for _ in range(3)]
            words = [base64.b64encode(line).decode() for line in lines]
            worker = subprocess.Popen([sys.executable, "-B", "-c", program, str(ROOT), str(folder), str(write), *words], stdout=subprocess.PIPE, text=True)
            self.assertEqual(worker.stdout.readline(), "half\n")
            worker.kill()
            worker.communicate()
            one = run.Pipeline(folder, SHOPS, LIMITS)
            with self.subTest(write=write):
                self.assertEqual([len(one._files(kind)) for kind in ("raw", "verdicts", "runs")], [write > 1, write > 2, 0])
                one.take(lines)
                done = one.run(story.closing())
                self.assertEqual((done.run, done.problems, done.counts["all"]["valid"]), (1, [], len(lines)))


if __name__ == "__main__":
    unittest.main()
