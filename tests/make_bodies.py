"""Writes examples/bodies.jsonl: bodies as bytes, and what webhook-platform and this pipeline both have to say of them.

"known" says how the answer is known. "test": it stands in OrderTests.cs of webhook-platform. "read": it follows from reading
Order.cs and has not been run in C# yet, so nobody should rely on it before that.
"""

import base64
import json
import pathlib

FILE = pathlib.Path(__file__).resolve().parents[1] / "examples" / "bodies.jsonl"
GOOD = '{"type":"order.placed","order":"N-1","sku":"BOX-S","quantity":2,"cents":1250,"placed_at":"2026-11-24T10:00:00Z"}'
FIELDS = {"type": '"order.placed"', "order": '"N-1"', "sku": '"BOX-S"', "quantity": "2", "cents": "1250", "placed_at": '"2026-11-24T10:00:00Z"'}
ORDER, NOT_JSON = "order", "not JSON, or a name in it stands twice"
IN_TESTS = {
    "order": ['""', '"N 1"', '"N\\u0000"', '"' + "N" * 41 + '"', "1", "null"],
    "sku": ['["BOX-S"]'],
    "quantity": ["0", "-1", "1000", "1.5", '"2"', "9" * 20],
    "cents": ["-1", "100000001"],
    "placed_at": ['"yesterday"', '"2026-11-24T10:00:00"', '"2026-11-24T10:00:00+01:00"', '"2026-02-30T10:00:00Z"'],
}
ONLY_READ = {
    "order": ['"N_1"', '"É-1"', '"N-1\\n"', '"Ｎ1"', "true"],
    "sku": ['"BOX S"', '""', "{}"],
    "quantity": ["true", "1.0", "1e2", "-0"],
    "cents": ["true", "1250.0", "1e3", '"1250"', "9" * 5000],
    "placed_at": [
        '"2026-11-24T24:00:00Z"', '"2026-11-24T23:59:60Z"', '"0000-01-01T00:00:00Z"', '"2026-11-24t10:00:00z"', '"2026-11-24T10:00:00.0Z"',
        '"2026-11-24 10:00:00Z"', '"2026-1-4T1:0:0Z"', '"٢026-11-24T10:00:00Z"', '"2026-11-24T10:00:00Z\\n"', "1764000000",
    ],
}


def changed(name, value):
    """The good body with another value in one field, or without it."""
    fields = {key: text for key, text in (FIELDS | {name: value}).items() if text is not None}
    return "{" + ",".join(f'"{key}":{text}' for key, text in fields.items()) + "}"


def first(text):
    """The good body with something in front of its first field."""
    return GOOD.replace("{", "{" + text + ",", 1)


def bodies():
    half = bytearray(GOOD.encode())
    half[half.index(b"N")] = 0xFF

    yield "an order", GOOD, ORDER, "test"
    yield "a field that is not known", first('"note":"x"'), ORDER, "test"
    yield "nothing at all", "", NOT_JSON, "test"
    yield "only the first character", "{", NOT_JSON, "test"
    yield "ten lists", "[" * 10 + "1" + "]" * 10, NOT_JSON, "test"
    yield "half a character in a name", '{"\\ud800":1}', NOT_JSON, "test"
    yield "half a character in the type", '{"type":"\\ud800"}', "not text", "test"
    yield "a byte that is not UTF-8 in a field that is read", bytes(half), "not text", "test"
    for text in ("null", "[]", '"order.placed"'):
        yield f"only {text}", text, "not an object", "test"
    yield "an empty object", "{}", "missing or wrong: type", "test"
    yield "a name twice", GOOD.replace('"cents":1250', '"cents":1250,"cents":1'), NOT_JSON, "test"
    yield "another type", GOOD.replace("placed", "eaten"), "not a type that is known", "test"
    for known, values in (("test", IN_TESTS), ("read", ONLY_READ)):
        for name, texts in values.items():
            for text in texts:
                yield f"{name} is {text if len(text) < 30 else text[:9] + '...'}", changed(name, text), f"missing or wrong: {name}", known
    for name in IN_TESTS:
        yield f"{name} is missing", changed(name, None), f"missing or wrong: {name}", "test"

    for text in ("NaN", "Infinity", "01", "+1", "1_000", "0x1"):
        yield f"cents is {text}", changed("cents", text), NOT_JSON, "read"
    yield "cents is 0", changed("cents", "0"), ORDER, "read"
    yield "cents is -0", changed("cents", "-0"), ORDER, "read"
    yield "cents is the largest", changed("cents", "100000000"), ORDER, "read"
    yield "quantity is the largest", changed("quantity", "999"), ORDER, "read"
    yield "order is the longest", changed("order", '"' + "N" * 40 + '"'), ORDER, "read"
    yield "a leap day", changed("placed_at", '"2028-02-29T23:59:59Z"'), ORDER, "read"
    yield "a BOM in front", b"\xef\xbb\xbf" + GOOD.encode(), NOT_JSON, "read"
    yield "UTF-16", GOOD.encode("utf-16-le"), NOT_JSON, "read"
    yield "spaces and line breaks around it", " \t\r\n" + GOOD + "\r\n", ORDER, "read"
    yield "a space that is none in JSON", " " + GOOD, NOT_JSON, "read"
    yield "a name twice, once as an escape", GOOD.replace('"cents":1250', '"cents":1250,"\\u0063ents":1'), NOT_JSON, "read"
    yield "a name twice inside a field that is not known", first('"note":{"a":1,"a":2}'), NOT_JSON, "read"
    yield "a name in other letters", GOOD.replace('"cents"', '"Cents"'), "missing or wrong: cents", "read"
    yield "a name in both letters", first('"Cents":1'), ORDER, "read"
    yield "the type, written with an escape", changed("type", '"\\u006frder.placed"'), ORDER, "read"
    yield "a name, written with an escape", GOOD.replace('"order":', '"\\u006frder":'), ORDER, "read"
    yield "the type in other letters", changed("type", '"Order.Placed"'), "not a type that is known", "read"
    yield "half a character in a field that is not known", first('"note":"\\ud800"'), ORDER, "read"
    yield "a byte that is not UTF-8 in a field that is not known", first('"note":"?"').encode().replace(b"?", b"\xff"), ORDER, "read"
    yield "a byte that is not UTF-8 in a name", first('"?":1').encode().replace(b"?", b"\xff"), NOT_JSON, "read"
    yield "a comma too many", GOOD.replace("}", ",}"), NOT_JSON, "read"
    yield "a comment behind it", GOOD + "//x", NOT_JSON, "read"
    yield "two of them", GOOD + GOOD, NOT_JSON, "read"
    yield "only half of it", GOOD[: len(GOOD) // 2], NOT_JSON, "read"
    yield "a line break in a text", GOOD.replace("N-1", "N\n1"), NOT_JSON, "read"
    yield "as deep as is allowed", first('"note":' + "[" * 7 + "]" * 7), ORDER, "read"
    yield "one too deep", first('"note":' + "[" * 8 + "]" * 8), NOT_JSON, "read"
    yield "20,000 lists", "[" * 20_000, NOT_JSON, "read"


def lines():
    for name, body, says, known in bodies():
        body = body if isinstance(body, bytes) else body.encode()
        yield json.dumps({"name": name, "body": base64.b64encode(body).decode(), "says": says, "known": known}) + "\n"


if __name__ == "__main__":
    FILE.write_text("".join(lines()), encoding="utf-8")
