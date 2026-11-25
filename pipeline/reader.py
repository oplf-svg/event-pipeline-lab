"""Reads the body of an event as strictly as webhook-platform does (Order.cs). Both are tested with the same bodies.

It decides nothing about a day, a total or lateness. It only says whether a body is an order, and why not.
"""

import datetime
import json
import re

NOT_JSON = "not JSON, or a name in it stands twice"
CODE = re.compile(r"[A-Za-z0-9-]{1,40}")
WHOLE = re.compile(r"-?[0-9]{1,10}")
MOMENT = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z")
KNOWN = ("type", "order", "sku", "quantity", "cents", "placed_at")
DEEPEST = 8


class Unreadable(Exception):
    """The reason never repeats anything that stood in the body."""


class Number(str):
    """A number as it was written. Otherwise 1.0 and 1e2 would look whole, and very long ones would be refused in another way."""


def read(body):
    """Returns the order, or raises Unreadable with the reason."""
    try:
        # Not from bytes: there Python guesses UTF-16 and takes a BOM. A byte that is not UTF-8 is kept, because webhook-platform only
        # minds it in a field that it reads.
        root = _parsed(body.decode("utf-8", "surrogateescape"), _names_once)
        # Half a character that is written as an escape is minded in every name. So once more, without those bytes.
        if b"\\" in body:
            _parsed(body.decode("utf-8", "replace"), _names_whole)
    except (ValueError, RecursionError):
        raise Unreadable(NOT_JSON) from None
    if _depth(root) > DEEPEST:
        raise Unreadable(NOT_JSON)
    if not isinstance(root, dict):
        raise Unreadable("not an object")
    if _text(root, "type") != "order.placed":
        raise Unreadable("not a type that is known")
    return {
        "order": _code(root, "order"),
        "sku": _code(root, "sku"),
        "quantity": _whole(root, "quantity", 1, 999),
        "cents": _whole(root, "cents", 0, 100_000_000),
        "placed_at": _moment(root, "placed_at"),
        "unknown": sorted(root.keys() - set(KNOWN)),
    }


def _parsed(text, names):
    return json.loads(text, object_pairs_hook=names, parse_int=Number, parse_float=Number, parse_constant=_refuse)


def _refuse(word):
    # NaN and Infinity, which are no JSON.
    raise Unreadable(NOT_JSON)


def _names_once(pairs):
    found = dict(pairs)
    if len(found) != len(pairs):
        raise Unreadable(NOT_JSON)
    return found


def _names_whole(pairs):
    if any(_half(name) for name, _ in pairs):
        raise Unreadable(NOT_JSON)


def _half(text):
    """Half a character: written as an escape, or left over from a byte that is not UTF-8."""
    return any("\ud800" <= char <= "\udfff" for char in text)


def _depth(value):
    deepest, waiting = 0, [(value, 1)]
    while waiting:
        item, level = waiting.pop()
        if isinstance(item, (dict, list)):
            deepest = max(deepest, level)
            waiting += [(inner, level + 1) for inner in (item.values() if isinstance(item, dict) else item)]
    return deepest


def _wrong(name):
    return Unreadable(f"missing or wrong: {name}")


def _text(root, name):
    value = root.get(name)
    if not isinstance(value, str) or isinstance(value, Number):
        raise _wrong(name)
    if _half(value):
        raise Unreadable("not text")
    return value


def _code(root, name):
    value = _text(root, name)
    if not CODE.fullmatch(value):
        raise _wrong(name)
    return value


def _whole(root, name, least, most):
    value = root.get(name)
    if not isinstance(value, Number) or not WHOLE.fullmatch(value) or not least <= int(value) <= most:
        raise _wrong(name)
    return int(value)


def _moment(root, name):
    found = MOMENT.fullmatch(_text(root, name))
    if not found:
        raise _wrong(name)
    try:
        return datetime.datetime(*map(int, found.groups()), tzinfo=datetime.UTC)
    except ValueError:
        # It looks like a moment, but there is no 30 February.
        raise _wrong(name) from None
