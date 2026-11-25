"""The days of the shops: every moment is in exactly one, and the clocks are right."""

import datetime
import importlib.util
import unittest
import zoneinfo

from lab import SHOPS, Lab, feed

from pipeline import days, line


def micros(text):
    return line.micros(datetime.datetime.fromisoformat(text))


def days_of(shops, first, last, closes_at="06:00"):
    return list(days.rows(shops, range(micros(first), micros(last) + 1, 3_600_000_000), closes_at))


class Days(Lab):
    def test_every_moment_is_in_exactly_one_day(self):
        """Every half hour, and the microsecond before it, against a list of clock changes that was written by hand."""
        found = days_of(SHOPS, "2026-04-01T00:00Z", "2027-12-01T00:00Z")
        for shop in SHOPS:
            mine = [row for row in found if row[0] == shop]
            at = 0
            for us in range(micros("2026-04-02T00:00Z"), micros("2027-11-30T00:00Z"), 1_800_000_000):
                for moment in (us - 1, us):
                    while mine[at][3] <= moment:
                        at += 1
                    inside = [row[1] for row in mine[max(0, at - 2) : at + 3] if row[2] <= moment < row[3]]
                    self.assertEqual(inside, [feed.local_day(shop, moment)], f"{shop} {moment}")

    def test_12_how_many_hours_they_have(self):
        wanted = {
            "north": {"2026-03-29": 23, "2026-10-25": 25, "2027-03-28": 23, "2027-10-31": 25},
            "plaza": {"2026-03-29": 23, "2026-10-25": 25, "2027-03-28": 23, "2027-10-31": 25},
            "harbour": {"2026-03-08": 23, "2026-11-01": 25, "2027-03-14": 23, "2027-11-07": 25},
        }
        found = {shop: {} for shop in SHOPS}
        for shop, day, begins, ends, _ in days_of(SHOPS, "2026-01-03T00:00Z", "2027-12-29T00:00Z"):
            if (hours := (ends - begins) / 3_600_000_000) != 24:
                found[shop][day] = hours
        self.assertEqual(found, wanted)

    def test_13_what_the_clock_on_the_wall_says(self):
        """Against a list of clock changes that was written by hand."""
        for shop, day, begins, ends, closes in days_of(SHOPS, "2026-04-01T00:00Z", "2027-12-01T00:00Z"):
            following = (datetime.date.fromisoformat(day) + days.ONE).isoformat()
            self.assertEqual((begins, ends, closes), (feed.moment(shop, day), feed.moment(shop, following), feed.moment(shop, f"{following}T06:00:00")), f"{shop} {day}")

    def test_13_a_shop_that_moves(self):
        """A day ends when the next one begins, whatever the clock said before. So no moment is lost and none counts twice."""
        for zones, hours in (
            ([["2020-01-01", "Europe/London"], ["2027-02-10", "America/New_York"]], 29),
            ([["2020-01-01", "Europe/London"], ["2027-02-01", "Europe/London"], ["2027-02-10", "America/New_York"], ["2027-05-01", "Europe/Madrid"]], 29),
            ([["2020-01-01", "America/New_York"], ["2027-02-10", "Europe/London"]], 19),
            ([["2027-02-10", "Europe/London"], ["2020-01-01", "America/New_York"]], 19),
        ):
            found = days_of({"mover": zones}, "2027-02-01T00:00Z", "2027-02-20T00:00Z")
            self.assertEqual({day: (ends - begins) / 3_600_000_000 for _, day, begins, ends, _ in found if ends - begins != 86_400_000_000}, {"2027-02-09": hours})

    def test_13_the_last_day_before_a_move_is_closed_by_the_new_clock(self):
        """It is closed at 6 in the morning of the next day, and on that one the shop has moved."""
        for zones, closes in (
            ([["2020-01-01", "Europe/London"], ["2027-02-10", "America/New_York"]], {"2027-02-08": "2027-02-09T06:00Z", "2027-02-09": "2027-02-10T11:00Z", "2027-02-10": "2027-02-11T11:00Z"}),
            ([["2020-01-01", "America/New_York"], ["2027-02-10", "Europe/London"]], {"2027-02-08": "2027-02-09T11:00Z", "2027-02-09": "2027-02-10T06:00Z", "2027-02-10": "2027-02-11T06:00Z"}),
        ):
            found = {day: us for _, day, _, _, us in days_of({"mover": zones}, "2027-02-01T00:00Z", "2027-02-20T00:00Z")}
            self.assertEqual({day: found[day] for day in closes}, {day: micros(text) for day, text in closes.items()})

    def test_12_a_midnight_that_stands_twice_or_never(self):
        """In Havana the clock was changed at midnight. A day begins at the first 0:00, and where there is none, when it would have been."""
        found = {day: (begins, ends) for _, day, begins, ends, _ in days_of({"island": [["2020-01-01", "America/Havana"]]}, "2024-03-01T00:00Z", "2024-11-20T00:00Z")}
        for day, begins, ends in (
            ("2024-03-09", "2024-03-09T05:00Z", "2024-03-10T05:00Z"), ("2024-03-10", "2024-03-10T05:00Z", "2024-03-11T04:00Z"), ("2024-03-11", "2024-03-11T04:00Z", "2024-03-12T04:00Z"),
            ("2024-11-02", "2024-11-02T04:00Z", "2024-11-03T04:00Z"), ("2024-11-03", "2024-11-03T04:00Z", "2024-11-04T05:00Z"), ("2024-11-04", "2024-11-04T05:00Z", "2024-11-05T05:00Z"),
        ):
            self.assertEqual(found[day], (micros(begins), micros(ends)), day)

    def test_09_the_hour_at_which_a_day_is_closed(self):
        for hour, closes in (("06:00", "2027-07-02T05:00Z"), ("06:30", "2027-07-02T05:30Z"), ("00:00", "2027-07-01T23:00Z"), ("23:59", "2027-07-02T22:59Z")):
            found = {day: us for shop, day, _, _, us in days_of({"north": SHOPS["north"]}, "2027-06-25T00:00Z", "2027-07-05T00:00Z", hour)}
            self.assertEqual(found["2027-07-01"], micros(closes), hour)

    @unittest.skipUnless(importlib.util.find_spec("tzdata"), "the pinned list of clock rules is not here")
    def test_the_list_of_clock_rules_is_the_pinned_one(self):
        self.assertEqual(zoneinfo.TZPATH, ())

    def test_a_shop_that_is_not_there_yet_has_no_days(self):
        found = days_of({"new": [["2027-02-10", "Europe/London"]]}, "2027-02-01T00:00Z", "2027-02-20T00:00Z")
        self.assertEqual(found[0][1], "2027-02-10")

    def test_every_moment_has_its_day_wherever_the_shop_is(self):
        shops = {"east": [["2020-01-01", "Pacific/Kiritimati"]], "west": [["2020-01-01", "Pacific/Pago_Pago"]], "moved": [["2020-01-01", "Pacific/Apia"], ["2027-02-10", "Pacific/Pago_Pago"]]}
        for hour in range(0, 96, 1):
            at = micros("2027-02-08T00:00Z") + hour * 3_600_000_000
            found = [row for row in days.rows(shops, [at], "06:00") if row[2] <= at < row[3]]
            self.assertEqual([row[0] for row in found].count("east"), 1)
            self.assertEqual(sorted(row[0] for row in found), ["east", "moved", "west"], f"hour {hour}")

    def test_no_moment_no_day(self):
        self.assertEqual(list(days.rows(SHOPS | {"old": [["1960-01-01", "Europe/London"]]}, [], "06:00")), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
