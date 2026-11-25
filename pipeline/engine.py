"""The engines that run the rules. The same text has to give the same answers in each of them."""

import base64
import csv
import pathlib
import sqlite3
import tempfile

KINDS = {"text": "varchar", "whole": "bigint", "bytes": "blob"}


def quoted(path):
    """A path inside a statement."""
    return "'" + str(path).replace("'", "''") + "'"


class Sqlite:
    name = "sqlite"

    def __init__(self):
        self.db = sqlite3.connect(":memory:")

    def table(self, name, columns, rows):
        rows = list(rows)
        self.db.execute(f"create table {name} ({', '.join(f'{column} {KINDS[kind]}' for column, kind in columns)})")
        if rows:
            self.fill(name, columns, rows)

    def fill(self, name, columns, rows):
        self.db.executemany(f"insert into {name} values ({', '.join('?' * len(columns))})", rows)

    def rule(self, name, text):
        self.db.execute(f"create table {name} as\n{text}")

    def ask(self, question):
        return self.db.execute(question).fetchall()


class Duck(Sqlite):
    name = "duckdb"

    def __init__(self):
        import duckdb

        # It must not fetch anything while it runs.
        self.db = duckdb.connect(":memory:", config={"autoinstall_known_extensions": "false", "autoload_known_extensions": "false"})

    def fill(self, name, columns, rows):
        # Through a file, because value by value takes some hundred times as long. Nothing is guessed: the kinds are said, what is
        # not there is empty, and an empty text stands in quotes.
        of_bytes = [kind == "bytes" for _, kind in columns]
        if any(of_bytes):
            rows = [[base64.b64encode(value).decode() if is_bytes else value for value, is_bytes in zip(row, of_bytes, strict=True)] for row in rows]
        # By itself it refuses rows above 2 MB. Whoever sends a long line would stop all lines that come with it.
        longest = max(sum(len(value.encode()) + value.count('"') for value in row if isinstance(value, str)) for row in rows) + 100 * len(columns)
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder, "rows.csv")
            with open(path, "w", encoding="utf-8", newline="") as file:
                csv.writer(file, quoting=csv.QUOTE_NOTNULL).writerows(rows)
            kinds = ", ".join(f"'{column}': '{KINDS['text'] if kind == 'bytes' else KINDS[kind]}'" for column, kind in columns)
            picked = ", ".join(f"from_base64({column})" if kind == "bytes" else column for column, kind in columns)
            self.db.execute(
                f"insert into {name} select {picked} from read_csv({quoted(path)}, columns = {{{kinds}}}, header = false, auto_detect = false,"
                f" delim = ',', quote = '\"', escape = '\"', nullstr = '', allow_quoted_nulls = false, parallel = false, max_line_size = {max(longest, 2_097_152)})"
            )


def all_of_them():
    """Each engine that is here. Where every one has to be there, the tests say so."""
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return [Sqlite]
    return [Sqlite, Duck]
