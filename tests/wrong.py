"""Proves that the tests can fail: puts one mistake at a time into a copy of the reader, and looks whether they notice it.

Each mistake names what has to notice it, every time. The random bodies notice some of them as well, but a check that depends
on luck would prove nothing. Every one of these mistakes is easy to make. The unchanged copy has to pass first, because
otherwise a failure would prove nothing.

    python wrong.py           all of them
    python wrong.py 2/4       the second of four parts
    python wrong.py NAME...   only these
"""

import dataclasses
import os
import pathlib
import sys
import tempfile

import looks


@dataclasses.dataclass(frozen=True)
class Wrong:
    """One mistake: what it is, which examples have to notice it ("holds: cents" is a value of an order), and the change."""

    name: str
    what: str
    noticed_by: tuple[str, ...]
    changes: tuple[tuple[str, str], ...]

    def put_into(self, text):
        for old, new in self.changes:
            if text.count(old) != 1:
                raise ValueError(f"{self.name}: stands {text.count(old)} times in the reader: {old}")
            text = text.replace(old, new)
        return text


def change(name, what, noticed_by, *changes):
    return Wrong(name, what, noticed_by, changes)


LOADS = "json.loads(text, object_pairs_hook=names, parse_int=Number, parse_float=Number, parse_constant=_refuse)"
DECODE = 'body.decode("utf-8", "surrogateescape")'
TEXT = "if not isinstance(value, str) or isinstance(value, Number):"
WHOLE = "if not isinstance(value, Number) or not WHOLE.fullmatch(value) or not least <= int(value) <= most:"
TWICE, HALVES = "if len(found) != len(pairs):", "if any(_half(name) for name, _ in pairs):"
MOMENT = 'MOMENT = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z")'
FOUND = "found = MOMENT.fullmatch(_text(root, name))"
CODE = 'CODE = re.compile(r"[A-Za-z0-9-]{1,40}")'

ALL = [
    # The bytes.
    change("bytes.guessed", "Python guesses how the bytes are meant", ("a BOM in front",), (DECODE, "body")),
    change("bytes.utf16", "UTF-16 is read as well", ("UTF-16",), (DECODE, 'body.decode("utf-16-le" if b"\\0" in body else "utf-8", "surrogateescape")')),
    change("bytes.strict", "Any byte that is not UTF-8 makes it unreadable", ("a byte that is not UTF-8 in a field that is read", "a byte that is not UTF-8 in a field that is not known", "a byte that is not UTF-8 in a name"), (DECODE, 'body.decode("utf-8")')),
    change("bytes.lost", "What is not UTF-8 is left out", ("a byte that is not UTF-8 in a field that is read", "two names that differ in a byte that is not UTF-8"), (DECODE, 'body.decode("utf-8", "ignore")')),
    change("bytes.bom", "A BOM is passed over", ("a BOM in front",), (DECODE, 'body.decode("utf-8-sig", "surrogateescape")')),
    change("bytes.trimmed", "Every kind of space around it is taken off", ("a space that is none in JSON",), (DECODE, 'body.decode("utf-8", "surrogateescape").strip()')),
    # The JSON.
    change("json.last_wins", "Of a name that stands twice, the last one wins", ("a name twice", "a name twice, once as an escape", "a name twice inside a field that is not known"), (TWICE, "if False:")),
    change("json.first_level", "Only the names of the first level have to differ", ("a name twice inside a field that is not known",), (TWICE, 'if len(found) != len(pairs) and "type" in found:')),
    change("json.any_name", "A name may be half a character", ("half a character in a name", "a name with half a character and a byte that is not UTF-8"), (HALVES, "if False:")),
    change("json.byte_in_a_name", "A byte that is not UTF-8 is minded in a name", ("a byte that is not UTF-8 in a name", "two names that differ in a byte that is not UTF-8"), (TWICE, "if len(found) != len(pairs) or any(_half(name) for name in found):")),
    change("json.bytes_alike", "All bytes that are not UTF-8 are the same", ("two names that differ in a byte that is not UTF-8",), (DECODE, 'body.decode("utf-8", "replace")')),
    change("json.nan", "NaN and Infinity are numbers", ("cents is NaN", "cents is Infinity"), (", parse_constant=_refuse)", ")")),
    change("json.rest", "What stands behind the first object does not matter", ("two of them", "a comment behind it"), (LOADS, "json.JSONDecoder(object_pairs_hook=names, parse_int=Number, parse_float=Number, parse_constant=_refuse).raw_decode(text.lstrip(' \\t\\r\\n'))[0]")),
    change("json.control", "A line break may stand in a text", ("a line break in a text",), (", parse_constant=_refuse)", ", parse_constant=_refuse, strict=False)")),
    change("json.no_floor", "A body that is too deep for Python breaks the reader", ("the deepest body there can be",), ("except (ValueError, RecursionError):", "except ValueError:")),
    change("json.depth", "Any depth is fine", ("one too deep",), ("    if _depth(root) > DEEPEST:\n        raise Unreadable(NOT_JSON)\n", "")),
    change("json.depth_less", "One level less is allowed", ("as deep as is allowed",), ("DEEPEST = 8", "DEEPEST = 7")),
    change("json.depth_more", "One level more is allowed", ("one too deep",), ("DEEPEST = 8", "DEEPEST = 9")),
    change("json.depth_in_lists", "Objects in lists are no depth", ("one too deep, with objects in lists",), ("item.values() if isinstance(item, dict) else item)]", "item.values() if isinstance(item, dict) else [inner for inner in item if isinstance(inner, list)])]")),
    change("json.depth_of_lists", "Only lists count as depth", ("one too deep",), ("if isinstance(item, (dict, list)):\n            deepest = max(deepest, level)", "if isinstance(item, (dict, list)):\n            level -= isinstance(item, dict)\n            deepest = max(deepest, level)")),
    change("json.not_an_object", "Nobody looks whether it is an object", ("only null", "only []", 'only "order.placed"'), ('    if not isinstance(root, dict):\n        raise Unreadable("not an object")\n', "")),
    # The type.
    # Which reason is said.
    change("first.type_last", "The type is looked at last", ("type and order are missing",), ('    if _text(root, "type") != "order.placed":\n        raise Unreadable("not a type that is known")\n    return {', '    found = {'), ('        "unknown": sorted(root.keys() - set(KNOWN)),\n    }\n', '        "unknown": sorted(root.keys() - set(KNOWN)),\n    }\n    if _text(root, "type") != "order.placed":\n        raise Unreadable("not a type that is known")\n    return found\n')),
    change("first.sku", "The sku is looked at first", ("order and sku are missing", "half a character in the sku, and the order is missing"), ('    return {\n        "order"', '    _code(root, "sku")\n    return {\n        "order"')),
    change("first.quantity", "The quantity is looked at before the sku", ("sku and quantity are missing",), ('        "sku": _code(root, "sku"),', '        "quantity": _whole(root, "quantity", 1, 999),\n        "sku": _code(root, "sku"),')),
    change("first.cents", "The cents are looked at before the quantity", ("quantity and cents are missing",), ('        "quantity": _whole(root, "quantity", 1, 999),', '        "cents": _whole(root, "cents", 0, 100_000_000),\n        "quantity": _whole(root, "quantity", 1, 999),')),
    change("first.moment", "The moment is looked at before the cents", ("cents and placed_at are missing",), ('        "cents": _whole(root, "cents", 0, 100_000_000),', '        "placed_at": _moment(root, "placed_at"),\n        "cents": _whole(root, "cents", 0, 100_000_000),')),
    change("type.any", "Every type is an order", ("another type, and all else as it should be", "the type in other letters"), ('    if _text(root, "type") != "order.placed":\n        raise Unreadable("not a type that is known")\n', '    _text(root, "type")\n')),
    change("type.family", "Every type that begins with order is one", ("another type, and all else as it should be",), ('if _text(root, "type") != "order.placed":', 'if not _text(root, "type").startswith("order."):')),
    change("type.letters", "Large and small letters of the type are the same", ("the type in other letters",), ('if _text(root, "type") != "order.placed":', 'if _text(root, "type").lower() != "order.placed":')),
    change("type.as_written", "The type is compared as it was written", ("the type, written with an escape",), ('if _text(root, "type") != "order.placed":', 'if _text(root, "type") != "order.placed" or b\'"order.placed"\' not in body:')),
    change("type.optional", "A type that is missing is an order", ("an empty object",), ('if _text(root, "type") != "order.placed":', 'if root.setdefault("type", "order.placed") and _text(root, "type") != "order.placed":')),
    # The fields.
    change("fields.letters", "Large and small letters of a name are the same", ("a name in other letters",), ("found = dict(pairs)", "found = {name.lower(): value for name, value in pairs}")),
    change("fields.unknown_refused", "A field that is not known makes it unreadable", ("a field that is not known",), ('"unknown": sorted(root.keys() - set(KNOWN)),', '"unknown": sorted(root.keys() - set(KNOWN)) and _text(root, ""),')),
    change("fields.unknown_unsaid", "A field that is not known is passed over without a word", ("holds: unknown",), ("sorted(root.keys() - set(KNOWN))", "[]")),
    change("fields.swapped", "Quantity and cents are swapped", ("holds: quantity", "holds: cents"), ('"quantity": _whole(root, "quantity", 1, 999)', '"quantity": _whole(root, "cents", 0, 100_000_000)'), ('"cents": _whole(root, "cents", 0, 100_000_000)', '"cents": _whole(root, "quantity", 1, 999)')),
    change("fields.says_what_stood_there", "The reason repeats what stood in the body", ('order is "N 1"', 'sku is "BOX S"'), ("if not CODE.fullmatch(value):\n        raise _wrong(name)", "if not CODE.fullmatch(value):\n        raise _wrong(f'{name}: {value}')")),
    # Texts and codes.
    change("text.numbers", "A number is a text", ("order is 1",), (TEXT, "if not isinstance(value, str):")),
    change("text.half", "Half a character is a text", ("half a character in the type", "a byte that is not UTF-8 in a field that is read"), ('    if _half(value):\n        raise Unreadable("not text")\n', "")),
    change("text.half_first", "Only the first halves of characters are halves", ("order is \\udc00", "order is \\udfff"), ('"\\ud800" <= char <= "\\udfff"', '"\\ud800" <= char <= "\\udbff"')),
    change("text.half_second", "Only the second halves of characters are halves", ("order is \\udbff",), ('"\\ud800" <= char <= "\\udfff"', '"\\udc00" <= char <= "\\udfff"')),
    change("text.half_of_bytes", "Only what stands for a byte that is not UTF-8 is a half", ("order is \\udd00", "order is \\udc7f"), ('"\\ud800" <= char <= "\\udfff"', '"\\ud800" <= char <= "\\udbff" or "\\udc80" <= char <= "\\udcff"')),
    change("names.half_at_the_top", "Half a character is only minded in a name at the top", ("half a character in a name further in",), ("if any(_half(name) for name, _ in pairs):", 'if any(_half(name) for name, _ in pairs) and (len(pairs) == 1 or "type" in dict(pairs)):')),
    change("code.any_letter", "Letters and digits of every alphabet are allowed", ('order is "É-1"', 'order is "Ｎ1"'), (CODE, 'CODE = re.compile(r"[^\\W_-]?[\\w-]{0,39}(?<!_)")'), ("if not CODE.fullmatch(value):", 'if not value or "_" in value or not CODE.fullmatch(value):')),
    change("code.underscore", "An underscore is allowed", ('order is "N_1"',), (CODE, 'CODE = re.compile(r"[A-Za-z0-9_-]{1,40}")')),
    change("code.space", "A space is allowed", ('order is "N 1"', 'sku is "BOX S"'), (CODE, 'CODE = re.compile(r"[A-Za-z0-9 -]{1,40}")')),
    change("code.empty", "It may be empty", ('order is ""', 'sku is ""'), (CODE, 'CODE = re.compile(r"[A-Za-z0-9-]{0,40}")')),
    change("code.longer", "It may be one longer", ("order is " + '"NNNNNNNN' + "...",), (CODE, 'CODE = re.compile(r"[A-Za-z0-9-]{1,41}")')),
    change("code.shorter", "It has to be one shorter", ("order is the longest",), (CODE, 'CODE = re.compile(r"[A-Za-z0-9-]{1,39}")')),
    change("code.line_end", "A line break at its end is allowed", ('order is "N-1\\n"',), ("if not CODE.fullmatch(value):", 'if not re.match(CODE.pattern + "$", value):')),
    change("code.beginning", "Only its beginning is looked at", ('order is "N 1"', 'order is "N_1"'), ("if not CODE.fullmatch(value):", "if not CODE.match(value):")),
    # Whole numbers.
    change("whole.python", "Numbers are what Python makes of them", ("quantity is true", "cents is true"), (", parse_int=Number, parse_float=Number", ""), (WHOLE, "if not isinstance(value, int) or not least <= value <= most:")),
    change("whole.float", "1.0 is a whole number", ("quantity is 1.0", "cents is 1250.0"), (WHOLE, "if not isinstance(value, Number) or len(value) > 12 or float(value) != int(float(value)) or not least <= float(value) <= most:"), ("return int(value)\n", "return int(float(value))\n")),
    change("whole.text", "A number may stand in quotes", ('quantity is "2"', 'cents is "1250"'), (WHOLE, "if not isinstance(value, str) or not WHOLE.fullmatch(value) or not least <= int(value) <= most:")),
    change("whole.any_length", "A number of 5000 digits breaks the reader", ("cents is 999999999...",), ("{1,10}", "+")),
    change("whole.no_minus_zero", "-0 is no number", ("cents is -0",), ('r"-?[0-9]{1,10}"', 'r"-?[1-9][0-9]{0,9}|0"')),
    change("whole.quantity_0", "A quantity of 0 is allowed", ("quantity is 0", "quantity is -0"), ('"quantity", 1, 999', '"quantity", 0, 999')),
    change("whole.quantity_1000", "A quantity of 1000 is allowed", ("quantity is 1000",), ('"quantity", 1, 999', '"quantity", 1, 1000')),
    change("whole.quantity_998", "A quantity of 999 is not allowed", ("quantity is the largest",), ('"quantity", 1, 999', '"quantity", 1, 998')),
    change("whole.cents_1", "0 cents are not allowed", ("cents is 0", "cents is -0"), ('"cents", 0, 100_000_000', '"cents", 1, 100_000_000')),
    change("whole.cents_below", "Less than 0 cents are allowed", ("cents is -1",), ('"cents", 0, 100_000_000', '"cents", -1, 100_000_000')),
    change("whole.cents_more", "One cent more is allowed", ("cents is 100000001",), ("100_000_000", "100_000_001")),
    change("whole.cents_less", "One cent less is allowed", ("cents is the largest",), ("100_000_000", "99_999_999")),
    # Moments.
    change("moment.iso", "Any form of ISO 8601 is a moment", ('placed_at is "2026-11-24T10:00:00+01:00"', 'placed_at is "2026-11-24 10:00:00Z"', 'placed_at is "2026-11-24T10:00:00.0Z"'), (FOUND, "found = True"), ("datetime.datetime(*map(int, found.groups()), tzinfo=datetime.UTC)", "datetime.datetime.fromisoformat(_text(root, name)).astimezone(datetime.UTC)")),
    change("moment.strptime", "Days and hours may have one digit", ('placed_at is "2026-1-4T1:0:0Z"',), (FOUND, "found = True"), ("datetime.datetime(*map(int, found.groups()), tzinfo=datetime.UTC)", 'datetime.datetime.strptime(_text(root, name), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)')),
    change("moment.any_digit", "Digits of every alphabet are digits", ('placed_at is "٢026-11-24T10:00:00Z"',), (MOMENT, MOMENT.replace("[0-9]{4}", "\\d{4}"))),
    change("moment.letters", "Small letters are allowed in it", ('placed_at is "2026-11-24t10:00:00z"',), (MOMENT, MOMENT.replace('Z")', 'Z", re.IGNORECASE)'))),
    change("moment.line_end", "A line break at its end is allowed", ('placed_at is "2026-11-24T10:00:00Z\\n"',), (FOUND, 'found = re.match(MOMENT.pattern + "$", _text(root, name))')),
    change("moment.beginning", "Only its beginning is looked at", ('placed_at is "2026-11-24T10:00:00+01:00"',), (MOMENT, MOMENT.replace('Z")', 'Z?")')), (FOUND, "found = MOMENT.match(_text(root, name))")),
    change("moment.no_zone", "It may have no zone", ('placed_at is "2026-11-24T10:00:00"',), (MOMENT, MOMENT.replace('Z")', 'Z?")'))),
    change("moment.breaks", "A 30th of February breaks the reader", ('placed_at is "2026-02-30T10:00:00Z"', 'placed_at is "2026-11-24T24:00:00Z"', 'placed_at is "0000-01-01T00:00:00Z"'), ("    except ValueError:\n        # It looks", "    except KeyError:\n        # It looks")),
    change("moment.leap_second", "Second 60 becomes second 59", ('placed_at is "2026-11-24T23:59:60Z"',), ("*map(int, found.groups())", "*map(int, found.groups()[:5]), min(59, int(found[6]))")),
    change("moment.no_leap_day", "There is no 29th of February", ("a leap day",), ("found = MOMENT.fullmatch(_text(root, name))\n    if not found:", 'found = MOMENT.fullmatch(_text(root, name))\n    if not found or found[2] + found[3] == "0229":')),
    change("moment.naive", "It has no zone afterwards", ("holds: placed_at",), (", tzinfo=datetime.UTC", "")),
]


def noticed(text):
    """Everything that notices this reader, and whether it still reads a plain order at all."""
    with tempfile.TemporaryDirectory() as folder:
        path = pathlib.Path(folder, "reader.py")
        path.write_text(text, encoding="utf-8")
        reader = looks.load(path)
    found = set(looks.wrong_examples(reader)) | {f"holds: {name}" for name in looks.wrong_values(reader)} | set(looks.wrong_at_the_limit(reader))
    return found, not looks.says(reader, looks.examples()[0].body).startswith("broke")


def chosen(words):
    if len(words) == 1 and "/" in words[0]:
        part, parts = map(int, words[0].split("/"))
        if not 1 <= part <= parts:
            raise SystemExit("There is no such part.")
        return ALL[part - 1 :: parts]
    unknown = set(words) - {wrong.name for wrong in ALL}
    if unknown:
        raise SystemExit(f"There is no {', '.join(sorted(unknown))}.")
    return [wrong for wrong in ALL if not words or wrong.name in words]


def main(words):
    text = looks.READER.read_text(encoding="utf-8")
    if len({wrong.name for wrong in ALL}) != len(ALL):
        raise SystemExit("Two mistakes have the same name.")
    if noticed(text)[0]:
        raise SystemExit(f"The unchanged reader does not pass: {sorted(noticed(text)[0])}")
    lines, missed = ["| Mistake | Noticed |", "|---|---|"], 0
    for wrong in chosen(words):
        found, reads = noticed(wrong.put_into(text))
        left = [name for name in wrong.noticed_by if name not in found]
        answer = "no, it does not even read an order" if not reads else f"no: {', '.join(left)}" if left else "yes"
        missed += answer != "yes"
        lines.append(f"| {wrong.what} (`{wrong.name}`) | {answer} |")
        print(f"{answer:4} {wrong.name}")
    lines.append(f"| **{len(lines) - 2} mistakes** | **{len(lines) - 2 - missed}** |")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    print(f"{len(lines) - 3} mistakes, {missed} not noticed")
    return missed > 0 or len(lines) <= 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
