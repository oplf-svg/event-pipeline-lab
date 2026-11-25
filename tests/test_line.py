"""One line: what was sent is read, and nothing else is."""

import base64
import hashlib
import json
import random

from lab import Lab, feed

from pipeline import line

# What webhook-platform takes at most.
LARGEST = 262_144
EVERY_LETTER = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-"
GOOD = {"v": 1, "shop": "north", "n": 7, "feed": "north-web", "event_id": "evt_7", "received_at": "2027-03-28T22:59:59.123456Z", "body": "e30="}


def signed(said):
    said = said if isinstance(said, bytes) else json.dumps(said, separators=(",", ":")).encode()
    return hashlib.sha256(said).hexdigest().encode() + b" " + said


# Nobody but the sender can make these, but a mistake of the sender has to show as well.
NO_LINES = {
    "another version": GOOD | {"v": 2},
    "a version that is true": GOOD | {"v": True},
    "no number": GOOD | {"n": None},
    "number 0": GOOD | {"n": 0},
    "a number below 0": GOOD | {"n": -1},
    "a number that is true": GOOD | {"n": True},
    "a number in quotes": GOOD | {"n": "7"},
    "half a number": GOOD | {"n": 7.5},
    "a whole number with a fraction": GOOD | {"n": 7.0},
    "no number at all": GOOD | {"n": float("nan")},
    "a number without an end": GOOD | {"n": float("inf")},
    "a version with a fraction": GOOD | {"v": 1.0},
    "a number with a point": signed(GOOD)[65:].replace(b'"n":7', b'"n":7.0'),
    "a number that is too large": GOOD | {"n": 2**53},
    "a shop in large letters": GOOD | {"shop": "North"},
    "no shop": GOOD | {"shop": ""},
    "a shop that is a list": GOOD | {"shop": ["north"]},
    "a shop with a line break": GOOD | {"shop": "north\n"},
    "a shop that is too long": GOOD | {"shop": "n" * 41},
    "a feed that is too long": GOOD | {"feed": "n" * 41},
    "no feed": GOOD | {"feed": ""},
    "no id": GOOD | {"event_id": ""},
    "a feed with a slash": GOOD | {"feed": "north/web"},
    "an id with a dot": GOOD | {"event_id": "evt.7"},
    "an id that is too long": GOOD | {"event_id": "e" * 101},
    "a time without its zone": GOOD | {"received_at": "2027-03-28T22:59:59.123456"},
    "a time in another zone": GOOD | {"received_at": "2027-03-28T22:59:59.123456+01:00"},
    "a time in whole seconds": GOOD | {"received_at": "2027-03-28T22:59:59Z"},
    "a time long ago": GOOD | {"received_at": "1999-12-31T23:59:59.999999Z"},
    "a time that nobody will see": GOOD | {"received_at": "2200-01-01T00:00:00.000000Z"},
    "a time that is none": GOOD | {"received_at": "2027-02-30T22:59:59.123456Z"},
    "a body that is not base64": GOOD | {"body": "e30"},
    "a body with a line break": GOOD | {"body": "e30=\n"},
    "a body in another base64": GOOD | {"body": "e31="},
    "a body that is an object": GOOD | {"body": {}},
    "a body that is too large": GOOD | {"body": base64.b64encode(b"x" * (LARGEST + 1)).decode()},
    "a field less": {name: value for name, value in GOOD.items() if name != "feed"},
    "a field more": GOOD | {"more": 1},
    "other names": {("number" if name == "n" else name): value for name, value in GOOD.items()},
    "another order of its fields": dict(reversed(GOOD.items())),
    "a name twice": b'{"v":1,' + signed(GOOD)[66:],
    "not an object": list(GOOD.values()),
    "a list of its names and values": [list(pair) for pair in GOOD.items()],
    "null": b"null",
    "true": b"true",
    "a number alone": b"7",
    "a text alone": b'"north"',
    "not JSON": b"north",
    "nothing": b"",
    "not UTF-8": signed(GOOD)[65:].replace(b"north-web", b"north\xffweb"),
    "a BOM": b"\xef\xbb\xbf" + signed(GOOD)[65:],
    "too deep": b"[" * LARGEST,
}
# The name of a field, what is just allowed there, and what has to be read.
JUST_ALLOWED = [
    *(("n", n, n) for n in (1, 10, 1000, 2**31 - 1, 2**31, 2**53 - 1)),
    *((name, value, value) for name in ("shop", "feed") for value in ("n", "0", "-", "n" * 40, "abcdefghijklmnopqrstuvwxyz0123456789-")),
    *(("event_id", value, value) for value in ("e", "_", ":", "e" * 100, EVERY_LETTER)),
    ("received_at", "2000-01-01T00:00:00.000000Z", 946_684_800_000_000), ("received_at", "2199-12-31T23:59:59.999999Z", 7_258_118_399_999_999),
    ("received_at", "2035-02-28T23:59:59.000001Z", 2_056_320_000 * 1_000_000 - 999_999), ("received_at", "2028-02-29T00:00:00.500000Z", 1_835_395_200_500_000),
    ("body", "", b""), ("body", base64.b64encode(b"x" * LARGEST).decode(), b"x" * LARGEST),
]


class Lines(Lab):
    def test_a_line_is_read(self):
        self.assertEqual(line.read(signed(GOOD)), line.Line("north", 7, "north-web", "evt_7", 1_806_274_799_123_456, b"{}"))

    def test_01_every_single_bit_counts(self):
        good = feed.Story().order().line
        for at in range(len(good)):
            for bit in range(8):
                changed = bytearray(good)
                changed[at] ^= 1 << bit
                with self.subTest(f"byte {at}, bit {bit}"), self.assertRaises(line.Spoiled):
                    line.read(bytes(changed))

    def test_01_every_cut_and_everything_added_counts(self):
        good = feed.Story().order().line
        for at in range(len(good)):
            with self.subTest(f"cut at {at}"), self.assertRaises(line.Spoiled):
                line.read(good[:at])
        for more in (b" ", b"\n", b"}", b"\0"):
            for changed in (good + more, more + good, good[:64] + more + good[64:], good[:65] + more + good[65:]):
                with self.subTest(more), self.assertRaises(line.Spoiled):
                    line.read(changed)

    def test_a_right_fingerprint_does_not_make_a_line(self):
        for what, said in NO_LINES.items():
            with self.subTest(what), self.assertRaises(line.Spoiled):
                line.read(signed(said))

    def test_what_is_just_allowed(self):
        for name, value, read in JUST_ALLOWED:
            with self.subTest(name, value=value[:50] if isinstance(value, str) else value):
                self.assertEqual(getattr(line.read(signed(GOOD | {name: value})), "received_us" if name == "received_at" else name), read)

    def test_any_bytes_can_be_a_body(self):
        body = bytes(random.Random(1).randbytes(LARGEST))
        self.assertEqual(line.read(feed.line("north", 1, "north-web", "evt_1", feed.moment("north", "2027-03-10T12:00:00"), body)).body, body)


if __name__ == "__main__":
    import unittest

    unittest.main()
