"""The days of a shop as rows: from when, until when, and when a day is closed.

The rules in SQL only compare whole numbers. So a day with 23 hours is a row like any other, and no engine needs rules for clocks
of its own.
"""

import datetime
import functools
import importlib.util
import zoneinfo

from pipeline import line

# The pinned list of clock rules, and not the one that this machine happens to have.
if importlib.util.find_spec("tzdata"):
    zoneinfo.reset_tzpath(to=[])

ONE = datetime.timedelta(days=1)
DAY_US = 86_400_000_000


def check(shops, closes_at):
    """Refuses at once what would go wrong later: in silence, or in the middle of a night."""
    hour = datetime.time.fromisoformat(closes_at)
    if hour.strftime("%H:%M") != closes_at:
        raise ValueError(f"{closes_at} is no hour and minute")
    for shop, zones in shops.items():
        if not line.NAME.fullmatch(shop):
            raise ValueError(f"{shop!r} is no name of a shop")
        if not zones or len({since for since, _ in zones}) < len(zones):
            raise ValueError(f"{shop} has no clock, or two from the same day on")
        for since, zone in zones:
            if datetime.date.fromisoformat(since).isoformat() != since or not "2000-01-01" <= since <= "2199-12-31":
                raise ValueError(f"{shop}: {since} is no date, or one that no line can have")
            if zone not in _clocks():
                raise ValueError(f"{shop}: there is no clock {zone}")
        for since, _ in zones:
            around = [datetime.date.fromisoformat(since) + step * ONE for step in (-2, -1, 0, 1, 2)]
            for time in (datetime.time(), hour):
                moments = [_at(zones, day, time) for day in around if _zone(zones, day)]
                if moments != sorted(set(moments)):
                    raise ValueError(f"{shop}: on {since} it moves to where the day before has not begun, or was not closed")


@functools.cache
def _clocks():
    return zoneinfo.available_timezones()


def rows(shops, moments, closes_at):
    """shop, day, from, to, closes: for every day in which one of the moments can lie. They are microseconds since 1970, and "to"
    belongs to the next day."""
    hour = datetime.time.fromisoformat(closes_at)
    dates = {line.EPOCH.date() + (us // DAY_US) * ONE for us in moments}
    # On no clock on earth it is more than one day earlier or later than in UTC.
    for day in sorted({date + step * ONE for date in dates for step in (-1, 0, 1)}):
        for shop, zones in shops.items():
            if _zone(zones, day):
                yield shop, day.isoformat(), _at(zones, day, datetime.time()), _at(zones, day + ONE, datetime.time()), _at(zones, day + ONE, hour)


def _zone(zones, day):
    """The zone that a shop has on a day. It has one from a date on, until the next one begins."""
    begun = [zone for since, zone in sorted(zones) if since <= day.isoformat()]
    return begun[-1] if begun else None


def _at(zones, day, time):
    return _moment(_zone(zones, day), day, time)


@functools.lru_cache(maxsize=None)
def _moment(zone, day, time):
    return line.micros(datetime.datetime.combine(day, time, zoneinfo.ZoneInfo(zone)).astimezone(datetime.UTC))
