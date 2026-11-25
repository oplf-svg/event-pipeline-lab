"""One line of the hand-over, as the exporter of webhook-platform is to send it:

    <64 hex> {"v":1,"shop":"north","n":1042,"feed":"north-web","event_id":"evt_7","received_at":"2027-03-28T22:59:59.123456Z","body":"<base64>"}

The 64 hex are the SHA-256 of everything behind the space. A fingerprint of the body alone would not see a changed shop.
"""

import base64
import dataclasses
import datetime
import hashlib
import json
import re

FIELDS = ["v", "shop", "n", "feed", "event_id", "received_at", "body"]
NAME = re.compile(r"[a-z0-9-]{1,40}")
ID = re.compile(r"[A-Za-z0-9_:-]{1,100}")
MOMENT = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.([0-9]{6})Z")
# What webhook-platform takes at most.
LARGEST = 256 * 1024
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
# From the beginning of 2000 to the end of 2199. Other moments are nobody's, and some programs cannot write them.
FIRST_US, LAST_US = 946_684_800_000_000, 7_258_118_400_000_000


class Object(list):
    """The names and values of an object. A list of pairs would look the same."""


class Spoiled(Exception):
    """It is not what was sent, or it cannot be read. The reason never repeats anything that stood in it."""


@dataclasses.dataclass(frozen=True)
class Line:
    shop: str
    n: int
    feed: str
    event_id: str
    received_us: int
    body: bytes


def micros(moment):
    """Microseconds since 1970, as a whole number. No engine has an opinion of its own about those."""
    return (moment - EPOCH) // datetime.timedelta(microseconds=1)


def read(record):
    given, space, said = record[:64], record[64:65], record[65:]
    if space != b" " or hashlib.sha256(said).hexdigest().encode() != given:
        raise Spoiled("its fingerprint does not fit")
    try:
        pairs = json.loads(said.decode("utf-8"), object_pairs_hook=Object)
        if not isinstance(pairs, Object) or [name for name, _ in pairs] != FIELDS:
            raise ValueError
        version, shop, n, feed, event_id, received_at, body = (value for _, value in pairs)
        if type(version) is not int or version != 1 or type(n) is not int or not 1 <= n < 2**53:
            raise ValueError
        if not NAME.fullmatch(shop) or not NAME.fullmatch(feed) or not ID.fullmatch(event_id):
            raise ValueError
        moment = datetime.datetime(*map(int, MOMENT.fullmatch(received_at).groups()), tzinfo=datetime.UTC)
        if not FIRST_US <= micros(moment) < LAST_US:
            raise ValueError
        bytes_of_it = base64.b64decode(body)
        # What is written in another way is not what was sent: Python passes over what is no base64, and the last bits are spare.
        if base64.b64encode(bytes_of_it).decode() != body or len(bytes_of_it) > LARGEST:
            raise ValueError
    except (ValueError, TypeError, AttributeError, RecursionError):
        raise Spoiled("it cannot be read") from None
    return Line(shop, n, feed, event_id, micros(moment), bytes_of_it)
