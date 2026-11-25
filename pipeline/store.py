"""What is kept in files: raw lines exactly as they arrived, and what became of them. Every file is written once."""

import base64
import json
import os
import pathlib
import secrets
import tempfile

from pipeline import engine


def put(path, data):
    """Writes a file that is not there yet, all of it or nothing, and comes back when it is on the disk. If it is there already, that is
    an error, whatever it holds."""
    made(path.parent)
    # A name with a dot in front: nothing that reads the folder takes it for a finished file.
    part = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    try:
        with open(part, "xb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.link(part, path)
        on_disk(path.parent)
    finally:
        part.unlink(missing_ok=True)


def made(folder):
    """Makes a folder that is not there yet, and comes back when it is on the disk."""
    if not folder.is_dir():
        made(folder.parent)
        try:
            folder.mkdir(exist_ok=True)
        except FileExistsError:
            # Not the same as a file that somebody else has written already.
            raise NotADirectoryError(f"{folder.name!a} is no folder") from None
        on_disk(folder.parent)


def on_disk(folder):
    """The name of a file stands in its folder. If the power fails it is there only if that was on the disk as well."""
    place = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(place)
    finally:
        os.close(place)


class Plain:
    """Needs nothing but Python. A line is kept as base64, so that no byte in it can end it."""

    name, ending = "plain", ".txt"

    @staticmethod
    def of_lines(lines):
        return b"".join(base64.b64encode(line) + b"\n" for line in lines)

    @staticmethod
    def lines(data):
        return [base64.b64decode(line, validate=True) for line in _ended(data)]

    @staticmethod
    def of_rows(columns, rows):
        return b"".join(json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in [[name for name, _ in columns], *rows])

    @staticmethod
    def rows(data):
        return [json.loads(line) for line in _ended(data)[1:]]


def _ended(data):
    *lines, rest = data.split(b"\n")
    if rest:
        raise ValueError("the last line has no end")
    return lines


class Parquet:
    """The same in files that many engines read. Here only DuckDB does. Only text, whole numbers and one column of bytes: the engines have
    opinions of their own about everything else. The numbers of the fields let a table format take the files over later, as they are."""

    name, ending = "parquet", ".parquet"

    @classmethod
    def of_lines(cls, lines):
        return cls.of_rows([("place", "whole"), ("line", "bytes")], list(enumerate(lines, 1)))

    @classmethod
    def lines(cls, data):
        return [line for _, line in cls.rows(data)]

    @staticmethod
    def of_rows(columns, rows):
        with tempfile.TemporaryDirectory() as folder:
            path, db = pathlib.Path(folder, "table.parquet"), engine.Duck()
            db.table("t", columns, rows)
            numbers = ", ".join(f"{name}: {number}" for number, (name, _) in enumerate(columns, 1))
            db.ask(f"copy (select * from t order by all) to {engine.quoted(path)} (format parquet, field_ids {{{numbers}}})")
            return path.read_bytes()

    @staticmethod
    def rows(data):
        """Sorted by the first column, then by the next one, and so on. A file of this kind has no order of its own."""
        import duckdb

        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder, "table.parquet")
            path.write_bytes(data)
            try:
                return [list(row) for row in engine.Duck().ask(f"select * from read_parquet({engine.quoted(path)}) order by all")]
            except duckdb.Error:
                raise ValueError("it is no Parquet") from None
