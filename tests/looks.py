"""Looks at a reader from outside: what it says of each example, and what must never come out of it."""

import base64
import collections
import datetime
import importlib.util
import json
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parents[1]
READER = ROOT / "pipeline" / "reader.py"
FIELDS = ("type", "order", "sku", "quantity", "cents", "placed_at")
# What webhook-platform takes at most.
LARGEST = 256 * 1024
NOT_JSON = "not JSON, or a name in it stands twice"
REASONS = {NOT_JSON, "not an object", "not text", "not a type that is known", *(f"missing or wrong: {name}" for name in FIELDS)}
PIECES = [piece.encode() for piece in ('"', "{", "}", "[", "]", ",", ":", "\\", "\\u0000", "\\ud800", "\\udc00", "1e999", "-0", "é", "null", "true", "9999999999")]

Example = collections.namedtuple("Example", "name body says known")


def examples():
    with open(ROOT / "examples" / "bodies.jsonl", encoding="utf-8") as file:
        rows = [json.loads(line) for line in file]
    return [Example(row["name"], base64.b64decode(row["body"]), row["says"], row["known"]) for row in rows]


def load(path):
    spec = importlib.util.spec_from_file_location("a_reader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def says(reader, body):
    """"order", the reason why it is none, or that the reader broke."""
    try:
        reader.read(body)
    except reader.Unreadable as reason:
        return str(reason)
    except Exception as problem:
        return f"broke: {type(problem).__name__}"
    return "order"


def wrong_examples(reader, of=None):
    """Name: what was said instead of what."""
    found = {}
    for example in examples() if of is None else of:
        said = says(reader, example.body)
        if said != example.says:
            found[example.name] = f"{said!r} instead of {example.says!r}"
    return found


def wrong_values(reader):
    """What an order holds, field by field."""
    body = b'{"placed_at":"2027-03-28T22:59:59Z","note":1,"cents":1250,"more":[],"sku":"BOX-S","quantity":2,"order":"N-1","type":"order.placed"}'
    wanted = {"order": "N-1", "sku": "BOX-S", "quantity": 2, "cents": 1250, "placed_at": datetime.datetime(2027, 3, 28, 22, 59, 59, tzinfo=datetime.UTC), "unknown": ["more", "note"]}
    try:
        got = reader.read(body)
    except Exception as problem:
        return {"all": f"broke: {type(problem).__name__}"}
    return {name: f"{got.get(name)!r} instead of {value!r}" for name, value in wanted.items() if got.get(name) != value or type(got.get(name)) is not type(value)} | {
        name: "made up" for name in got.keys() - wanted.keys()
    }


def wrong_at_the_limit(reader):
    """The deepest body there can be. It is too large for the file of examples, and how deep is too deep for Python itself is
    different in each version."""
    said = says(reader, b"[" * LARGEST)
    return {} if said == NOT_JSON else {"the deepest body there can be": said}


def strange_answers(reader, seed, rounds):
    """Changes a good body at random. Whatever comes, it is an order or one of the reasons. And what is called an order must
    look like one to somebody who reads it in another way."""
    chance, found = random.Random(seed), {}
    good = examples()[0].body
    for _ in range(rounds):
        body = bytearray(good)
        for _ in range(chance.randint(1, 4)):
            at = chance.randrange(len(body))
            match chance.randrange(4):
                case 0:
                    body[at] = chance.randrange(256)
                case 1:
                    del body[at : at + chance.randint(1, 5)]
                case 2:
                    body[at:at] = chance.choice(PIECES)
                case _:
                    body[at:at] = body[at : at + chance.randint(1, 29)]
            body = body or bytearray(1)
        said = says(reader, bytes(body))
        if said == "order":
            said = "order" if _looks_like_one(bytes(body)) else "not an order, and called one"
        if said != "order" and said not in REASONS:
            found.setdefault(said, bytes(body).hex())
    return found


def _looks_like_one(body):
    plain = json.loads(body.decode("utf-8", "replace"))
    whole = all(type(plain[name]) is int and least <= plain[name] <= most for name, least, most in (("quantity", 1, 999), ("cents", 0, 100_000_000)))
    return whole and plain["type"] == "order.placed" and all(type(plain[name]) is str and plain[name].isascii() for name in ("order", "sku", "placed_at"))


if __name__ == "__main__":
    all_of_them = examples()
    print("| The strict reader | |\n|---|---|")
    print(f"| Bodies it was asked about | {len(all_of_them)} |")
    for known, meaning in (("test", "whose answer stands in a test of webhook-platform"), ("read", "whose answer was not run in C# yet")):
        print(f"| of them, {meaning} | {sum(example.known == known for example in all_of_them)} |")
    print(f"| Answered as they should be | {len(all_of_them) - len(wrong_examples(load(READER)))} |")
