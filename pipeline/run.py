"""Judges what arrived, and writes down what it did. A run is red if its numbers do not add up, or if a file or list that a list
names is not as it was."""

import collections
import hashlib
import importlib.metadata
import json
import pathlib
import platform
import re
import sqlite3
import time

from pipeline import days, engine, line, reader, store

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES = ("lines", "valid", "marks", "verdicts")
ARRIVED = [
    ("place", "whole"), ("spoiled", "whole"), ("shop", "text"), ("n", "whole"), ("feed", "text"), ("line_print", "text"),
    ("event_print", "text"), ("body_print", "text"), ("received_us", "whole"), ("says", "text"), ("order_print", "text"),
    ("cents", "whole"), ("placed_us", "whole"), ("more_fields", "whole"),
]
DAYS = [("shop", "text"), ("shop_day", "text"), ("from_us", "whole"), ("to_us", "whole"), ("closes_us", "whole")]
VERDICTS = [
    ("place", "whole"), ("shop", "text"), ("n", "whole"), ("verdict", "text"), ("reason", "text"), ("shop_day", "text"),
    ("cents", "whole"), ("late", "whole"), ("out_of_order", "whole"), ("more", "whole"), ("received_us", "whole"),
]
KINDS = ("valid", "duplicate", "bad", "waiting")
MARKS = ("late", "out_of_order", "more")

Came = collections.namedtuple("Came", [name for name, _ in ARRIVED])
Verdict = collections.namedtuple("Verdict", [name for name, _ in VERDICTS])
Result = collections.namedtuple("Result", "run rows counts problems witness")


class Red(Exception):
    """What lies in the folder is not what the runs before have left there, or another run was faster. Nothing is listed."""


def settings():
    """The shops with their clocks, and the limits. The tests read them here as well."""

    def once(pairs):
        if len(dict(pairs)) < len(pairs):
            raise ValueError("a name stands twice")
        return dict(pairs)

    return tuple(json.loads((ROOT / name).read_text(encoding="utf-8"), object_pairs_hook=once) for name in ("shops.json", "rules/limits.json"))


def check(shops, limits):
    days.check(shops, limits["closes_at"])
    # More than a hundred years back, or a year ahead, is a mistake and no limit.
    for name, most in (("oldest_days", 36_500), ("future_minutes", 525_600)):
        if type(limits[name]) is not int or not 0 <= limits[name] <= most:
            raise ValueError(f"{name} is no whole number from 0 to {most}")


def now_us():
    """By the clock of this machine."""
    return time.time_ns() // 1000


def check_closing(closing):
    """It comes from another program. Five minutes are between the clocks of two machines, and no closing is asked before its moment."""
    at_us, numbers = closing["at_us"], closing["numbers"]
    if type(at_us) is not int or not line.FIRST_US <= at_us < min(line.LAST_US, now_us() + 300_000_000):
        raise ValueError("this is no moment for a closing, or it has not come yet")
    if any(type(n) is not int or not 0 <= n < 2**53 or not line.NAME.fullmatch(shop) for shop, n in numbers.items()):
        raise ValueError("these are no numbers of shops")


def arrived(lines):
    """One row for each line, in the order of arrival. It says what is in a line and decides nothing."""
    for place, record in enumerate(lines, 1):
        try:
            found = line.read(record)
        except line.Spoiled:
            yield Came(place, 1, *[None] * (len(ARRIVED) - 2))
            continue
        says, order = "order", {}
        try:
            order = reader.read(found.body)
        except reader.Unreadable as reason:
            says = str(reason)
        event_print, order_print = (_print(f"{found.feed} {name}".encode()) for name in (found.event_id, order.get("order")))
        yield Came(
            place, 0, found.shop, found.n, found.feed, record[:64].decode(), event_print, _print(found.body), found.received_us, says, order_print,
            order.get("cents"), line.micros(order["placed_at"]) if order else None, len(order.get("unknown", ())),
        )


def judge(came, shops, limits, engine_of=engine.Sqlite):
    """The verdicts, as the rules give them. Whether they can be right is looked at afterwards, in another way."""
    oldest_us, future_us = limits["oldest_days"] * days.DAY_US, limits["future_minutes"] * 60_000_000
    # Only orders that can be valid need a day. Whoever writes the year 1 into an order gets none.
    moments = {one.placed_us for one in came if one.placed_us is not None and one.received_us - oldest_us <= one.placed_us <= one.received_us + future_us}
    db = engine_of()
    db.table("arrived", ARRIVED, came)
    db.table("shop_days", DAYS, days.rows(shops, moments, limits["closes_at"]))
    db.table("limits", [("oldest_us", "whole"), ("future_us", "whole")], [(oldest_us, future_us)])
    for name in RULES:
        db.rule(name, (ROOT / "rules" / f"{name}.sql").read_text(encoding="utf-8"))
    return [Verdict(*row) for row in db.ask(f"select {', '.join(Verdict._fields)} from verdicts order by place")]


def count(rows):
    """What the verdicts add up to, for each shop and in all. A spoiled line belongs to no shop."""
    found = {"all": collections.Counter(raw=0, cents=0, **dict.fromkeys(KINDS + MARKS, 0)), "reasons": collections.Counter()}
    for row in rows:
        for name in ("all", *([f"shop {row.shop}"] if row.shop else [])):
            into = found.setdefault(name, collections.Counter(raw=0, cents=0, **dict.fromkeys(KINDS + MARKS, 0)))
            into.update({"raw": 1, "cents": row.cents or 0, str(row.verdict): 1, **{mark: getattr(row, mark) or 0 for mark in MARKS}})
        found["reasons"][f"{row.verdict}: {row.reason}"] += 1
    return {name: dict(sorted(counter.items())) for name, counter in sorted(found.items())}


def problems(came, rows, shops, closing=None, before=None):
    """Why these verdicts cannot be right, or cannot be all. It is worked out from what came, and not from what the rules made of it.

    A closing is asked from the database of webhook-platform: at which moment it was asked, and up to which number each shop had
    received something before. Up to there nothing may be missing. What was received later may be here already, and is for the next
    closing. "Before" is what the runs before have said that were not red: their last verdicts, and their last closing."""
    found = []
    if [one.place for one in came] != [row.place for row in rows]:
        found.append("a line has no verdict, or more than one")
    elif wrong := [row.place for one, row in zip(came, rows, strict=True) if not _can_be(one, row)]:
        found.append(f"{len(wrong)} verdicts cannot be, the first is at place {wrong[0]}")
    for name, counted in count(rows).items():
        if name != "reasons" and counted["raw"] != sum(counted[kind] for kind in KINDS):
            found.append(f"{name}: raw is {counted['raw']}, and the verdicts are {sum(counted[kind] for kind in KINDS)}")
    shops_of, lines = collections.defaultdict(set), collections.defaultdict(set)
    for one in came:
        if not one.spoiled:
            shops_of[one.feed].add(one.shop)
            lines[one.shop, one.n].add(one.line_print)
    found += [f"{feed} is a feed of {' and '.join(sorted(of_it))}" for feed, of_it in shops_of.items() if len(of_it) > 1]
    found += [f"{shop}: {len(prints)} different lines have the number {n}" for (shop, n), prints in lines.items() if len(prints) > 1]
    announced = set() if closing is None else {shop for shop, n in closing["numbers"].items() if n}
    found += [f"{shop} has no clock" for shop in {shop for shop, _ in lines} | announced if shop not in shops]
    numbers = _numbers(came)
    found += [] if closing is None else _missing(numbers, closing) + _above(numbers, closing, "the closing")
    return sorted(found + ([] if before is None else _changed(rows, numbers, closing, *before)))


def _can_be(one, row):
    """Whether a verdict is about this line, and says all that belongs to it."""
    valid = row.verdict == "valid"
    marks = all(getattr(row, mark) in (0, 1) and (valid or not getattr(row, mark)) for mark in MARKS)
    return (
        (row.shop, row.n, row.received_us) == (one.shop, one.n, one.received_us) and row.verdict in KINDS and bool(row.reason) and marks
        and bool(one.spoiled) == (row.reason == "spoiled") and valid == (row.reason == "an order") == (row.shop_day is not None) and row.cents == (one.cents if valid else 0)
    )


def _numbers(came):
    """The numbers that came of each shop, and when they were received."""
    numbers = collections.defaultdict(dict)
    for one in came:
        if not one.spoiled:
            numbers[one.shop][one.n] = one.received_us
    return numbers


def _missing(numbers, closing):
    """What is not there although it was announced."""
    found = []
    for shop, last in sorted(closing["numbers"].items()):
        there = sorted(n for n in numbers.get(shop, ()) if n <= last)
        if missing := last - len(there):
            first = next((rank for rank, n in enumerate(there, 1) if n != rank), len(there) + 1)
            found.append(f"{shop}: {missing} of {last} numbers are missing, the first is {first}")
    return found


def _above(numbers, closing, which):
    """What was received before a closing, and not announced by it. It was asked too early."""
    found = []
    for shop, received in sorted(numbers.items()):
        last = closing["numbers"].get(shop, 0)
        if above := sum(n > last and received_us < closing["at_us"] for n, received_us in received.items()):
            found.append(f"{shop}: {above} numbers above the announced {last} were received before {which}")
    return found


def _changed(rows, numbers, closing, rows_before, closing_before):
    """What was said once stays, but that a line waits. Nothing that was announced is taken back, and nothing is added to it."""
    found = []
    if wrong := [old.place for old, new in zip(rows_before, rows) if old.verdict != "waiting" and old != new]:
        found.append(f"{len(wrong)} verdicts are not what they were, the first is at place {wrong[0]}")
    if closing_before is not None:
        found += _above(numbers, closing_before, "the closing before")
    if closing is not None and closing_before is not None:
        if closing["at_us"] < closing_before["at_us"]:
            found.append("the closing before was asked at a later moment")
        for shop, last in sorted(closing_before["numbers"].items()):
            now = closing["numbers"].get(shop, 0)
            if now < last or now > last and closing["at_us"] == closing_before["at_us"]:
                found.append(f"{shop}: {now} are announced, and {last} were in the closing before")
    return found


class Pipeline:
    """A folder with three kinds of files, each written once: raw lines, verdicts, and one list for each run. The list names every
    file with its fingerprint, and the list before it. Nothing in the folder vouches for the last list. Its fingerprint is the
    witness of a run, and has to be kept by somebody else."""

    def __init__(self, folder, shops, limits, engine_of=engine.Sqlite, store_of=store.Plain):
        check(shops, limits)
        self.folder, self.shops, self.limits, self.engine_of, self.store = pathlib.Path(folder), shops, limits, engine_of, store_of

    def take(self, lines):
        """Keeps lines as they arrived, before anybody has looked at them. The beginning of their fingerprint is in the name of the
        file, so that it shows if its content is another one before a run has listed it."""
        data, number = self.store.of_lines(lines), len(self._files("raw")) + 1
        while True:
            try:
                return store.put(self.folder / "raw" / f"{number:06}-{_print(data)[:16]}{self.store.ending}", data)
            except FileExistsError:
                # Somebody else took the same lines at the same moment. Both are kept.
                number += 1

    def run(self, closing=None, witness=None):
        if closing is not None:
            check_closing(closing)
        past = self._past()
        # A run can die after its list was written and before anybody has seen its witness. Then the one before it is still there.
        if witness is not None and witness not in ["", *(print_of_it for print_of_it, _ in past)][-2:]:
            raise Red("the last list is not the one that the witness has seen")
        raw, lines = self._raw(past[-1][1]["raw"] if past else [])
        came = list(arrived(lines))
        self._look_at_last(past, came, witness)
        one, tables, rows = self._made(past, raw, came, self.shops, self.limits, closing)
        for kind, table in tables.items():
            one[kind] = self._keep(kind, one["run"], table)
        data = _written(one)
        try:
            store.put(self.folder / "runs" / f"{one['run']:06}.json", data)
        except FileExistsError:
            raise Red(f"another run was faster, and it is run {one['run']}") from None
        return Result(one["run"], rows, one["counts"], one["problems"], _print(data))

    def _made(self, past, raw, came, shops, limits, closing):
        """What a run says, what it keeps, and its verdicts. The same lines and settings give the same once more."""
        rows = judge(came, shops, limits, self.engine_of)
        one = {
            "run": len(past) + 1, "before": past[-1][0] if past else "", "raw": raw, "counts": count(rows), "closing": closing,
            "problems": problems(came, rows, shops, closing, self._before(past)), "shops": shops, "limits": limits, "program": program(), "clock": clock(),
        }
        return one, {"verdicts": self.store.of_rows(VERDICTS, [list(row) for row in rows])}, rows

    def _keep(self, kind, number, data):
        """Its fingerprint is in its name. What a run left that died is named by no list, and is in nobody's way."""
        more = 0
        while True:
            name = f"{number:06}-{_print(data)[:16]}{f'-{more}' if more else ''}{self.store.ending}"
            try:
                store.put(self.folder / kind / name, data)
            except FileExistsError:
                if (self.folder / kind / name).read_bytes() != data:
                    more += 1
                    continue
            return {"file": name, "sha256": _print(data)}

    def _past(self):
        """The list of each run so far with its fingerprint, each looked at against the one before and the files it names."""
        past = []
        for number, path in enumerate(self._files("runs"), 1):
            try:
                data = path.read_bytes()
                one = json.loads(data)
                follows = path.name == f"{number:06}.json" and one["before"] == (past[-1][0] if past else "")
                grows = not past or one["raw"][: len(past[-1][1]["raw"])] == past[-1][1]["raw"]
                if not follows or not grows or not _are_files(one["raw"]):
                    raise Red(f"runs/{path.name!a} does not follow the run before it")
                if not self._was_kept("verdicts", number, one["verdicts"]):
                    raise Red(f"the verdicts of run {number} were changed")
            except (ValueError, KeyError, TypeError, AttributeError, OSError, RecursionError):
                raise Red(f"runs/{path.name!a} cannot be read, or its verdicts are gone") from None
            past.append((_print(data), one))
        return past

    def _was_kept(self, kind, number, one):
        """Whether a file lies under the name that its run gave it, and is what was listed."""
        name = rf"{number:06}-{re.escape(one['sha256'][:16])}(-[0-9]+)?\{self.store.ending}"
        return re.fullmatch(name, one["file"]) and _print((self.folder / kind / one["file"]).read_bytes()) == one["sha256"]

    def _raw(self, listed):
        """The lines of all raw files: first those that are listed, as they were listed, and then the new ones."""
        paths, known = {path.name: path for path in self._files("raw")}, {one["file"]: one for one in listed}
        raw, lines = [], []
        for name in [*known, *sorted(paths.keys() - known.keys())]:
            if name not in paths:
                raise Red(f"raw/{name!a} is gone")
            try:
                data = paths[name].read_bytes()
            except OSError:
                raise Red(f"raw/{name!a} cannot be read") from None
            if not re.fullmatch(rf"[0-9]{{6,}}-{_print(data)[:16]}\{self.store.ending}", name):
                raise Red(f"raw/{name!a} is not what was taken")
            try:
                fresh = self.store.lines(data)
            except ValueError:
                raise Red(f"raw/{name!a} cannot be read") from None
            one = {"file": name, "lines": len(fresh), "sha256": _print(data)}
            if known.get(name, one) != one:
                raise Red(f"raw/{name!a} is not what was listed")
            raw.append(one)
            lines += fresh
        return raw, lines

    def _look_at_last(self, past, came, witness):
        """Nobody has listed the last list. If somebody has seen it, that is enough. Otherwise it has to be what comes out once more of
        the same lines and settings, and only the program that wrote it can say that."""
        if not past or witness == past[-1][0]:
            return
        print_of_it, last = past[-1]
        if (last.get("program"), last.get("clock")) != (program(), clock()):
            raise Red("the last list was written by another version of the program or with other clock rules, and no witness has seen it")
        try:
            if last["closing"] is not None:
                check_closing(last["closing"])
        except Exception:
            raise Red("the last list has a closing that is none, or whose moment has not come by the clock of this machine") from None
        try:
            check(last["shops"], last["limits"])
            one, tables, *_ = self._made(past[:-1], last["raw"], came[: sum(file["lines"] for file in last["raw"])], last["shops"], last["limits"], last["closing"])
            for kind, table in tables.items():
                one[kind] = {"file": last[kind]["file"], "sha256": _print(table)}
            fits = _print(_written(one)) == print_of_it
        except Exception as problem:
            # It may be nothing that this program has written, or there was no memory for it. That is not the same, so it is said which.
            raise Red(f"the last list cannot be worked out once more: {type(problem).__name__}") from None
        if not fits:
            raise Red("the last list is not what comes out of the same lines once more")

    def _before(self, past):
        """The verdicts of the last run that was not red, and the last closing. What is red has no say: otherwise it would be enough to
        be red once, and whatever was changed would be fine from then on."""
        green = [one for _, one in past if not one["problems"]]
        if not green:
            return None
        return self._verdicts(green[-1]), next((one["closing"] for one in reversed(green) if one["closing"] is not None), None)

    def _verdicts(self, one):
        try:
            return [Verdict(*row) for row in self.store.rows((self.folder / "verdicts" / one["verdicts"]["file"]).read_bytes())]
        except (ValueError, TypeError):
            raise Red(f"the verdicts of run {one['run']} have another form") from None

    def _files(self, kind):
        """Sorted by name. What begins with a dot was never finished. A folder that cannot be read is not an empty one, nor is a link that
        leads nowhere."""
        folder = self.folder / kind
        try:
            return sorted(path for path in folder.iterdir() if not path.name.startswith("."))
        except OSError as problem:
            if isinstance(problem, FileNotFoundError) and not folder.is_symlink():
                return []
            raise Red(f"{kind} cannot be read") from None


def _print(data):
    return hashlib.sha256(data).hexdigest()


def _written(one):
    return json.dumps(one, indent=1, sort_keys=True).encode() + b"\n"


def _are_files(raw):
    """Whether a list names files as it has to: each once, with its lines and its fingerprint."""
    kinds = all(set(one) == {"file", "lines", "sha256"} and type(one["lines"]) is int and one["lines"] >= 0 for one in raw)
    return kinds and len({one["file"] for one in raw}) == len(raw)


def program():
    """The fingerprint of each file that decides something, and what runs them."""
    files = [*(ROOT / "pipeline").glob("*.py"), *(ROOT / "rules").glob("*.sql")]
    found = {f"{path.parent.name}/{path.name}": _print(path.read_bytes()) for path in sorted(files)}
    return found | {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "duckdb": _version("duckdb")}


def clock():
    """Which list of clock rules was used."""
    version = _version("tzdata")
    return f"tzdata {version}" if version else "the one of this machine"


def _version(package):
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None
