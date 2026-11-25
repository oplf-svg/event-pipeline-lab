"""What really happened, told by somebody who knows, and how it was delivered. It uses nothing of the pipeline.

Every line is made here, together with what has to become of it: whoever adds a case says what the pipeline has to say about it.
Only what is out of order is worked out afterwards, because that depends on what else there is.
"""

import base64
import collections
import dataclasses
import datetime
import hashlib
import itertools
import json
import random

EPOCH = datetime.datetime(1970, 1, 1)


def micros(text):
    return (datetime.datetime.fromisoformat(text) - EPOCH) // datetime.timedelta(microseconds=1)


def _clock(*changes):
    """From a moment in UTC on, how many hours the clock of a place is ahead."""
    return [(micros(moment), hours * 3_600_000_000) for moment, hours in changes]


# Written down by hand, so that a mistake in anybody's list of clock rules shows.
CLOCKS = {
    "north": _clock(("2026-03-29T01:00", 1), ("2026-10-25T01:00", 0), ("2027-03-28T01:00", 1), ("2027-10-31T01:00", 0), ("2028-03-26T01:00", 1)),
    "plaza": _clock(("2026-03-29T01:00", 2), ("2026-10-25T01:00", 1), ("2027-03-28T01:00", 2), ("2027-10-31T01:00", 1), ("2028-03-26T01:00", 2)),
    "harbour": _clock(("2026-03-08T07:00", -4), ("2026-11-01T06:00", -5), ("2027-03-14T07:00", -4), ("2027-11-07T06:00", -5), ("2028-03-12T07:00", -4)),
}
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-"
CHANNELS = {"north": ("north-web", "north-phone"), "plaza": ("plaza-web", "plaza-market"), "harbour": ("harbour-web", "harbour-phone")}


def moment(shop, local):
    """Microseconds since 1970 for what the clock on the wall of a shop says. If it says so twice, the first time."""
    wall, clock = micros(local), CLOCKS[shop]
    for (begins, ahead), (ends, _) in itertools.pairwise(clock):
        if begins <= wall - ahead < ends:
            return wall - ahead
    raise ValueError(f"{local} is never on the wall of {shop}, or not in this list")


def local(shop, us):
    """What the calendar and the clock on the wall of a shop say at a moment."""
    ahead = next(hours for (begins, hours), (ends, _) in itertools.pairwise(CLOCKS[shop]) if begins <= us < ends)
    return EPOCH + datetime.timedelta(microseconds=us + ahead)


def local_day(shop, us):
    return local(shop, us).date().isoformat()


def written(us, places=6):
    return (EPOCH + datetime.timedelta(microseconds=us)).isoformat(timespec="microseconds" if places else "seconds") + "Z"


def body(number, placed_us, cents=1250, *, sku="BOX-S", quantity=1, more=(), without=(), **other):
    fields = {"type": "order.placed", "order": number, "sku": sku, "quantity": quantity, "cents": cents, "placed_at": written(placed_us, 0)}
    fields = {name: value for name, value in (fields | other).items() if name not in without} | dict(more)
    return json.dumps(fields).encode()


def line(shop, n, feed, event_id, received_us, body):
    said = {"v": 1, "shop": shop, "n": n, "feed": feed, "event_id": event_id, "received_at": written(received_us), "body": base64.b64encode(body).decode()}
    said = json.dumps(said, separators=(",", ":")).encode()
    return hashlib.sha256(said).hexdigest().encode() + b" " + said


@dataclasses.dataclass(frozen=True)
class Sent:
    """One line, and what has to become of it."""

    shop: str
    n: int
    feed: str
    event_id: str
    line: bytes
    body: bytes
    received_us: int
    placed_us: int | None = None
    verdict: str = "valid"
    reason: str = "an order"
    day: str | None = None
    cents: int = 0
    late: int = 0
    more: int = 0


class Story:
    def __init__(self, seed=0):
        self.chance, self.sent = random.Random(seed), []
        self.last, self._ids, self._numbers = collections.Counter(), itertools.count(1), itertools.count(1)

    def event(self, shop, received_us, body, *, feed=None, event_id=None, **becomes):
        self.last[shop] += 1
        n, feed = self.last[shop], feed or CHANNELS[shop][0]
        event_id = event_id or f"evt_{next(self._ids)}"
        self.sent.append(Sent(shop, n, feed, event_id, line(shop, n, feed, event_id, received_us, body), body, received_us, **becomes))
        return self.sent[-1]

    def order(self, shop="north", placed="2027-03-10T12:00:00", received=None, *, number=None, cents=1250, feed=None, event_id=None, verdict="valid", reason="an order", late=0, **of_body):
        """Both moments are what the clock on the wall of the shop says. Without the second one it was received two seconds later."""
        placed_us = moment(shop, placed)
        received_us = moment(shop, received) if received else placed_us + 2_000_000
        return self.placed(shop, placed_us, received_us, placed[:10], number=number, cents=cents, feed=feed, event_id=event_id, verdict=verdict, reason=reason, late=late, **of_body)

    def placed(self, shop, placed_us, received_us, day=None, *, number=None, cents=1250, feed=None, event_id=None, verdict="valid", reason="an order", late=0, **of_body):
        """The same with both moments in UTC. Without a day it is the one on the wall when it was placed."""
        good = verdict == "valid"
        return self.event(
            shop, received_us, body(number or f"N-{next(self._numbers)}", placed_us, cents, **of_body), feed=feed, event_id=event_id, verdict=verdict, reason=reason,
            placed_us=placed_us, day=(day or local_day(shop, placed_us)) if good else None, cents=cents if good else 0, late=late, more=1 if good and of_body.get("more") else 0,
        )

    def unreadable(self, shop, says, body, received="2027-03-10T12:00:00", **other):
        return self.event(shop, moment(shop, received), body, verdict="bad", reason=says, **other)

    def again(self, first, received_us=None):
        """The same event once more, under a number of its own."""
        return self.event(first.shop, received_us or first.received_us, first.body, feed=first.feed, event_id=first.event_id, verdict="duplicate", reason="the same event")

    def contradicted(self, first, body, seconds=5, received_us=None):
        """Another body under an id that is used."""
        return self.event(first.shop, received_us or first.received_us + seconds * 1_000_000, body, feed=first.feed, event_id=first.event_id, verdict="bad", reason="another body")

    def out_of_order(self):
        """The places in "sent" of the valid orders that come after one that was placed later."""
        newest, found = {}, set()
        for place, sent in enumerate(self.sent):
            if sent.verdict == "valid":
                if sent.placed_us < newest.get(sent.shop, sent.placed_us):
                    found.add(place)
                newest[sent.shop] = max(sent.placed_us, newest.get(sent.shop, sent.placed_us))
        return found

    def closing(self, at=None):
        """What the database of webhook-platform says at a moment, or after everything: how far the numbers of each shop go."""
        if at is None:
            return {"at_us": max((sent.received_us for sent in self.sent), default=0) + 1, "numbers": dict(self.last)}
        numbers = collections.Counter()
        for sent in self.sent:
            if sent.received_us < at:
                numbers[sent.shop] = max(numbers[sent.shop], sent.n)
        return {"at_us": at, "numbers": dict(numbers)}


SECOND, DAY = 1_000_000, 86_400_000_000


def everything(seed, size, first="2027-03-08", opened=None, asked=()):
    """A story over 22 days in which clocks are changed, told in the order in which it was received, but for a little disorder. Every
    case says what has to become of it. "Opened" is the first day of all shops, and "asked" are the moments at which a closing is asked."""
    story = Story(seed)
    chance, begin = story.chance, micros(first)
    used, firsts, seen = collections.defaultdict(list), collections.defaultdict(list), 0
    slots = [(begin + chance.randrange(22 * DAY), shop) for shop in chance.choices(list(CHANNELS), k=size)]
    # Exactly when a closing is asked, right before, and right after.
    slots += [(at_us + step, shop) for at_us in asked for shop in CHANNELS for step in (-1, 0, 1)]
    # Now and then something gets its number after others that were received later.
    slots.sort(key=lambda slot: slot[0] + (chance.randrange(7_200 * SECOND) if chance.random() < 0.1 else 0))
    exactly = {at_us + step for at_us in asked for step in (-1, 0, 1)}

    def some_time(until=24):
        # Not between 1 and 3 at night: there an hour can be missing or stand twice. Those have tests of their own.
        return f"{chance.choice([hour for hour in (0, *range(3, 24)) if hour < until]):02}:{chance.randrange(60):02}:{chance.randrange(60):02}"

    for received_us, shop in slots:
        for sent in story.sent[seen:]:
            if sent.reason not in ("the same event", "another body"):
                firsts[sent.shop].append(sent)
        seen = len(story.sent)
        wall, whole = local(shop, received_us), received_us // SECOND * SECOND
        six = moment(shop, f"{wall.date()}T06:00:00")
        channel, cents = chance.choice(CHANNELS[shop]), chance.choice([0, 1, *(chance.randrange(1, 50_000) for _ in range(8))])
        of_it = {"feed": channel, "cents": cents}

        def tell(placed_us, received_us, shop=shop, **becomes):
            """An order, unless its shop was not there on that day. That is said before anything is said of its number."""
            if opened and becomes.get("reason", "number used") == "number used" and local_day(shop, placed_us) < opened:
                becomes |= {"verdict": "bad", "reason": "no day for this shop", "late": 0}
            story.placed(shop, placed_us, received_us, **becomes)

        def days_ago(days, until=24, shop=shop, wall=wall):
            return moment(shop, f"{wall.date() - datetime.timedelta(days=days)}T{some_time(until)}")

        match 99 if received_us in exactly else chance.randrange(32):
            case 0:
                # Earlier on the same day, or in the night before its day is closed.
                until = wall.hour if wall.hour > 3 else 0
                tell(days_ago(0, until) if until else whole - 2 * SECOND, received_us, **of_it)
            case 1:
                tell(days_ago(1), received_us, late=int(received_us >= six), **of_it)
            case 2:
                tell(days_ago(chance.randrange(2, 34)), received_us, late=1, **of_it)
            case 3:
                # Exactly when its day is closed, and a moment before.
                tell(days_ago(1), six, late=1, **of_it)
            case 4:
                tell(days_ago(1), six - 1, **of_it)
            case 5:
                tell(whole - 35 * DAY, whole, late=1, **of_it)
            case 6:
                tell(whole - 35 * DAY, whole + 1, verdict="bad", reason="too old", **of_it)
            case 7:
                tell(days_ago(chance.randrange(37, 300)), received_us, verdict="bad", reason="too old", **of_it)
            case 8:
                # Ahead of time, sometimes of the next day.
                tell(whole + chance.randint(1, 300) * SECOND, received_us, **of_it)
            case 9:
                tell(whole + 300 * SECOND, whole, **of_it)
            case 10:
                tell(whole + 300 * SECOND, whole - 1, verdict="bad", reason="from the future", **of_it)
            case 11 if opened and (wall.date() - datetime.date.fromisoformat(opened)).days < 30:
                before = moment(shop, f"{datetime.date.fromisoformat(opened) - datetime.timedelta(days=1)}T{some_time()}")
                tell(before, max(received_us, before), verdict="bad", reason="no day for this shop", **of_it)
            case 12:
                tell(whole - 2 * SECOND, received_us, more=[("note", "x" * chance.randrange(40))], event_id="".join(chance.choices(LETTERS, k=94)) + f"{len(story.sent):06}", **of_it)
            case 13 | 14:
                says, text = chance.choice([
                    ("not JSON, or a name in it stands twice", b'{"type":'), ("not an object", b"[]"), ("not a type that is known", b'{"type":"order.eaten"}'),
                    ("missing or wrong: cents", body("N-1", 0, without=("cents",))), ("missing or wrong: quantity", body("N-1", 0, quantity=0)),
                    ("not text", b'{"type":"\\ud800"}'),
                ])
                story.event(shop, received_us, text, feed=channel, verdict="bad", reason=says)
            case 15 if firsts[shop]:
                story.again(chance.choice(firsts[shop]), received_us)
            case 16 if firsts[shop]:
                # It can even have been received before the other one. Its number is higher, and that alone counts.
                of_it = {"seconds": -5} if chance.random() < 0.2 else {"received_us": received_us}
                story.contradicted(firsts[shop][-1] if "seconds" in of_it else chance.choice(firsts[shop]), body(f"C-{len(story.sent)}", whole, cents), **of_it)
            case 17:
                number, other = f"B-{len(story.sent)}", CHANNELS[shop][1 - CHANNELS[shop].index(channel)]
                tell(whole - 2 * SECOND, received_us, number=number, **of_it)
                tell(whole - 2 * SECOND, received_us, number=number, **of_it | {"feed": other})
            case 18 if used[shop]:
                number, of_channel = chance.choice(used[shop])
                tell(whole - 2 * SECOND, received_us, number=number, verdict="bad", reason="number used", **of_it | {"feed": of_channel})
            case _:
                number = f"U-{len(story.sent)}"
                used[shop].append((number, channel))
                tell(whole - 2 * SECOND, received_us, number=number, **of_it)
    return story


def spoiled(sent, chance):
    """A copy in which one bit is another one, or that is cut, or stands twice without a break, or is nothing."""
    changed = bytearray(sent.line)
    match chance.randrange(8):
        case 0:
            return bytes(changed[: chance.randrange(len(changed))])
        case 1:
            return bytes(changed[chance.randrange(1, len(changed)) :])
        case 2:
            return sent.line + sent.line
        case 3:
            return chance.choice([b"", b"\n", b" ", sent.line + b"\n", sent.line + b" ", b" " + sent.line, chance.randbytes(40)])
    changed[chance.randrange(len(changed))] ^= 1 << chance.randrange(8)
    return bytes(changed)


@dataclasses.dataclass(frozen=True)
class Delivery:
    """What arrived: which line it was, and whether it is still that line."""

    place_in_story: int
    intact: bool
    line: bytes


def deliver(story, *, doubled=0.0, broken=0.0, dropped=(), shuffled=False):
    """Every line at least once, but for those whose place is in "dropped"."""
    chance, found = story.chance, []
    for place, sent in enumerate(story.sent):
        if place in dropped:
            continue
        found.append(Delivery(place, True, sent.line))
        while chance.random() < doubled:
            found.append(Delivery(place, True, sent.line))
        while chance.random() < broken:
            found.append(Delivery(place, False, spoiled(sent, chance)))
    if shuffled:
        chance.shuffle(found)
    return found
