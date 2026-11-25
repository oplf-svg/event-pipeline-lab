"""Writes examples/bodies.jsonl: bodies as bytes, and what webhook-platform and this pipeline both have to say of them.

"known" says how the answer is known. "test": it stands in OrderTests.cs of webhook-platform. "run": Order.cs of webhook-platform
(9ff662f) was asked once, by hand, on 24 and 25 November 2026.
"""

import base64
import itertools
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


def without(*names):
    """The good body without some of its fields."""
    return "{" + ",".join(f'"{key}":{text}' for key, text in FIELDS.items() if key not in names) + "}"


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
    for known, values in (("test", IN_TESTS), ("run", ONLY_READ)):
        for name, texts in values.items():
            for text in texts:
                yield f"{name} is {text if len(text) < 30 else text[:9] + '...'}", changed(name, text), f"missing or wrong: {name}", known
    for name in IN_TESTS:
        yield f"{name} is missing", changed(name, None), f"missing or wrong: {name}", "test"

    for text in ("NaN", "Infinity", "01", "+1", "1_000", "0x1"):
        yield f"cents is {text}", changed("cents", text), NOT_JSON, "run"
    yield "cents is 0", changed("cents", "0"), ORDER, "run"
    yield "cents is -0", changed("cents", "-0"), ORDER, "run"
    yield "cents is the largest", changed("cents", "100000000"), ORDER, "run"
    yield "quantity is the largest", changed("quantity", "999"), ORDER, "run"
    yield "order is the longest", changed("order", '"' + "N" * 40 + '"'), ORDER, "run"
    yield "a leap day", changed("placed_at", '"2028-02-29T23:59:59Z"'), ORDER, "run"
    yield "a BOM in front", b"\xef\xbb\xbf" + GOOD.encode(), NOT_JSON, "run"
    yield "UTF-16", GOOD.encode("utf-16-le"), NOT_JSON, "run"
    yield "spaces and line breaks around it", " \t\r\n" + GOOD + "\r\n", ORDER, "run"
    spread = [*(f'"{name}"\n:\t{text}' for name, text in FIELDS.items()), '"list":[ ]', '"object":{\r}', '"more" : [ 1 , [ ] , { "a" : { } } ]']
    yield "spaces and line breaks wherever they may be", "{ " + " ,\r\n".join(spread) + " }", ORDER, "run"
    yield "a space that is none in JSON", " " + GOOD, NOT_JSON, "run"
    yield "a name twice, once as an escape", GOOD.replace('"cents":1250', '"cents":1250,"\\u0063ents":1'), NOT_JSON, "run"
    yield "a name twice inside a field that is not known", first('"note":{"a":1,"a":2}'), NOT_JSON, "run"
    yield "a name in other letters", GOOD.replace('"cents"', '"Cents"'), "missing or wrong: cents", "run"
    yield "a name in both letters", first('"Cents":1'), ORDER, "run"
    yield "another type, and all else as it should be", changed("type", '"order.eaten"'), "not a type that is known", "run"
    yield "the type, written with an escape", changed("type", '"\\u006frder.placed"'), ORDER, "run"
    yield "a name, written with an escape", GOOD.replace('"order":', '"\\u006frder":'), ORDER, "run"
    yield "the type in other letters", changed("type", '"Order.Placed"'), "not a type that is known", "run"
    yield "half a character in a field that is not known", first('"note":"\\ud800"'), ORDER, "run"
    yield "a byte that is not UTF-8 in a field that is not known", first('"note":"?"').encode().replace(b"?", b"\xff"), ORDER, "run"
    # What webhook-platform said here was something else than what reading it had said.
    yield "a byte that is not UTF-8 in a name", first('"?":1').encode().replace(b"?", b"\xff"), ORDER, "run"
    yield "two names that differ in a byte that is not UTF-8", first('"?":1,"!":1').encode().replace(b"?", b"\xff").replace(b"!", b"\xfe"), ORDER, "run"
    yield "a name with a byte that is not UTF-8 twice", first('"?":1,"?":1').encode().replace(b"?", b"\xff"), NOT_JSON, "run"
    yield "a name with a byte that is not UTF-8 twice, once with an escape", first('"a?":1,"\\u0061?":1').encode().replace(b"?", b"\xff"), NOT_JSON, "run"
    yield "a name with half a character and a byte that is not UTF-8", first('"\\ud800?":1').encode().replace(b"?", b"\xff"), NOT_JSON, "run"
    # Of several things that are wrong, the first one is said.
    for name, following in itertools.pairwise(FIELDS):
        yield f"{name} and {following} are missing", without(name, following), f"missing or wrong: {name}", "run"
    yield "another type, and the order is missing", without("order").replace("placed", "eaten", 1), "not a type that is known", "run"
    yield "half a character in the order, and the sku is missing", without("sku").replace("N-1", "\\ud800"), "not text", "run"
    yield "half a character in the sku, and the order is missing", without("order").replace("BOX-S", "\\ud800"), "missing or wrong: order", "run"
    # Halves of characters.
    for half in ("\\udbff", "\\udc00", "\\udc7f", "\\udd00", "\\udfff", "\\udc00\\ud800", "\\ud83dN\\ude00"):
        yield f"order is {half}", changed("order", f'"{half}"'), "not text", "run"
    yield "order is one character that is written as two", changed("order", '"\\ud83d\\ude00"'), "missing or wrong: order", "run"
    yield "one character that is written as two in a field that is not known", first('"note":"\\ud83d\\ude00","\\ud83d\\ude00":1'), ORDER, "run"
    yield "half a character in a name further in", first('"note":{"a":[{"\\udc00":1,"b":2}]}'), NOT_JSON, "run"
    # The first and the last character of each length in UTF-8, and one that looks like a letter if half of it is lost.
    for char in "\x7f\x80\u07ff\u0800\uffff\U00010000\U0010ffff\u0141":
        yield f"order is U+{ord(char):04X}", changed("order", f'"{char}"'), "missing or wrong: order", "run"
    yield "every form of a number in a field that is not known", first('"note":[0,-0,-1,0.5,-0.25,1e2,1E2,1e+2,1E-2,-1.5e-10,12e00]'), ORDER, "run"
    for text in ("1e", "1e+", "1e+-2", "1.", ".5", "1.e2", "-", "-01", "2e1.5"):
        yield f"{text} in a field that is not known", first(f'"note":{text}'), NOT_JSON, "run"
    yield "a comma too many", GOOD.replace("}", ",}"), NOT_JSON, "run"
    yield "a comment behind it", GOOD + "//x", NOT_JSON, "run"
    yield "two of them", GOOD + GOOD, NOT_JSON, "run"
    yield "only half of it", GOOD[: len(GOOD) // 2], NOT_JSON, "run"
    yield "a line break in a text", GOOD.replace("N-1", "N\n1"), NOT_JSON, "run"
    yield "as deep as is allowed", first('"note":' + "[" * 7 + "]" * 7), ORDER, "run"
    yield "one too deep", first('"note":' + "[" * 8 + "]" * 8), NOT_JSON, "run"
    yield "as deep as is allowed, with objects in lists", first('"note":' + '[{"a":' * 3 + "[]" + "}]" * 3), ORDER, "run"
    yield "one too deep, with objects in lists", first('"note":' + '[{"a":' * 3 + "[{}]" + "}]" * 3), NOT_JSON, "run"
    yield "one too deep, with lists in objects", first('"note":' + '{"a":[' * 4 + "]}" * 4), NOT_JSON, "run"
    yield "20,000 lists", "[" * 20_000, NOT_JSON, "run"


def lines():
    for name, body, says, known in bodies():
        body = body if isinstance(body, bytes) else body.encode()
        yield json.dumps({"name": name, "body": base64.b64encode(body).decode(), "says": says, "known": known}) + "\n"


if __name__ == "__main__":
    FILE.write_text("".join(lines()), encoding="utf-8")
