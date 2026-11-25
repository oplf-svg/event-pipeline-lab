"""Each row of docs/contract.md alone, at a place that is known."""

import base64
import json

from lab import LIMITS, ROOT, SHOPS, Lab, count, feed, run

from outside.feed import Delivery, Story, body, deliver, moment


class Rows(Lab):
    def test_00_verdicts_that_cannot_be_right(self):
        """Whatever the rules do: one verdict for each line, about that line, and only what belongs together."""
        story = self.three()
        story.order(placed="2027-02-01T12:00:00", received="2027-03-10T12:00:00", verdict="bad", reason="too old")
        deliveries = [*deliver(story), Delivery(0, False, b"spoiled")]
        came = list(run.arrived([delivery.line for delivery in deliveries]))
        rows, _ = self.judged(deliveries)
        self.assertEqual(run.problems(came, rows, SHOPS, story.closing()), [])
        # However large a number is, nobody counts up to it.
        closing = story.closing()
        closing["numbers"]["plaza"] = 2**53
        self.assertEqual(run.problems(came, rows, SHOPS, closing), [f"plaza: {2**53 - 4} of {2**53} numbers are missing, the first is 5"])
        good, old, spoiled, nothing = 0, 12, 13, "a line has no verdict, or more than one"

        def other(place, **values):
            return [*rows[:place], rows[place]._replace(**values), *rows[place + 1 :]]

        for closing in (None, story.closing()):
            for what, wrong, said in (
                ("one less", rows[:-1], nothing), ("one twice", rows + rows[-1:], nothing), ("another one twice", rows[:-1] + rows[:1], nothing),
                ("two that changed places", [rows[1], rows[0], *rows[2:]], nothing), ("a fifth kind", other(good, verdict="late"), "all: raw is 14, and the verdicts are 13"),
                ("a fifth kind of a shop", other(good, verdict="late"), "shop north: raw is 5, and the verdicts are 4"),
                *((what, wrong, f"1 verdicts cannot be, the first is at place {place + 1}") for what, place, wrong in (
                    ("a fifth kind", good, other(good, verdict="late")), ("another shop", good, other(good, shop="plaza")), ("another number", good, other(good, n=9)),
                    ("another moment", good, other(good, received_us=1)), ("without a reason", old, other(old, reason=None)), ("an empty reason", old, other(old, reason="")),
                    ("valid without a day", good, other(good, shop_day=None)), ("valid with a reason why not", good, other(good, reason="too old")),
                    ("a cent more", good, other(good, cents=1251)), ("valid without cents", good, other(good, cents=None)), ("a mark that is nothing", good, other(good, late=None)), ("no verdict at all", good, other(good, verdict=None)), ("a mark that is 2", good, other(good, late=2)), ("bad with a day", old, other(old, shop_day="2027-02-01")),
                    ("a fifth kind that is not valid", old, other(old, verdict="late")), ("bad with cents", old, other(old, cents=1250)), ("bad, and late", old, other(old, late=1)), ("bad, and out of order", old, other(old, out_of_order=1)),
                    ("bad, and more", old, other(old, more=1)), ("an order that is bad", old, other(old, reason="an order")), ("spoiled and too old", spoiled, other(spoiled, reason="too old")),
                    ("too old and spoiled", old, other(old, reason="spoiled")), ("spoiled, with a shop", spoiled, other(spoiled, shop="north")),
                )),
            ):
                with self.subTest(what, closing=closing):
                    self.assertIn(said, run.problems(came, wrong, SHOPS, closing))

    def test_00_the_counter_sees_every_difference(self):
        """The counter outside is what everything is measured by. It sees each value of each verdict, and each problem."""
        story = self.three()
        story.order(placed="2027-03-10T12:30:00", more=[("note", "x")])
        arrived = deliver(story)
        rows, found = self.judged(arrived, story.closing())
        self.assertEqual(count.differences(story, arrived, rows, found), [])
        for place in (0, len(rows) - 1):
            for name, value in rows[place]._asdict().items():
                wrong = {"verdict": "bad", "reason": "too old", "shop": "harbour" if value != "harbour" else "north", "shop_day": "2027-03-11"}.get(name, None if isinstance(value, str) else value + 1)
                for changed in (wrong, None):
                    with self.subTest(name, place=place, changed=changed):
                        self.assertNotEqual(changed, value)
                        self.assertEqual(len(count.differences(story, arrived, [*rows[:place], rows[place]._replace(**{name: changed}), *rows[place + 1 :]], found)), 1)
        self.assertEqual(len(count.differences(story, arrived, rows[:-1], found)), 1)
        self.assertEqual(len(count.differences(story, arrived, rows, ["a problem"])), 1)
        self.assertEqual(len(count.differences(story, arrived, rows, [], ["a problem"])), 1)

    def three(self, seed=0):
        story = Story(seed)
        for shop in SHOPS:
            for _ in range(4):
                story.order(shop)
        return story

    def test_01_one_bit_is_flipped(self):
        for seed in range(40):
            story = self.three(seed)
            place = story.chance.randrange(len(story.sent))
            changed = feed.spoiled(story.sent[place], story.chance)
            with self.subTest(seed=seed):
                self.right(story, deliver(story) + [Delivery(place, False, changed)])

    def test_02_a_line_is_dropped(self):
        for place in range(12):
            story = self.three()
            lost = story.sent[place]
            behind = 4 - lost.n
            wanted = [f"{lost.shop}: 1 of 4 numbers are missing, the first is {lost.n}"]
            with self.subTest(place=place):
                rows = self.right(story, deliver(story, dropped={place}), wanted)
                self.assertEqual(run.count(rows)["all"]["waiting"], behind)

    def test_02_a_line_is_dropped_and_sent_again(self):
        story = self.three()
        self.right(story, deliver(story, dropped={1}) + [Delivery(1, True, story.sent[1].line)])

    def test_02_nothing_arrived_of_a_shop(self):
        story = self.three()
        self.right(story, deliver(story, dropped=set(range(4))), ["north: 4 of 4 numbers are missing, the first is 1"])

    def test_22_more_arrives_than_was_announced(self):
        story = self.three()
        closing = story.closing()
        closing["numbers"]["plaza"] -= 1
        self.assertEqual(self.judged(deliver(story), closing)[1], ["plaza: 1 numbers above the announced 3 were received before the closing"])
        del closing["numbers"]["plaza"]
        self.assertEqual(self.judged(deliver(story), closing)[1], ["plaza: 4 numbers above the announced 0 were received before the closing"])

    def test_22_what_was_received_after_the_closing_is_for_the_next_one(self):
        story = Story()
        for minute in (0, 1, 2, 3, 4):
            story.order(placed=f"2027-03-10T12:0{minute}:00")
        arrived, at = deliver(story), moment("north", "2027-03-10T12:02:02")
        self.assertEqual(story.closing(at)["numbers"], {"north": 2})
        for what, these, said in (
            ("all of it", arrived, []),
            ("what came before", arrived[:2], []),
            ("with a gap behind it", arrived[:2] + arrived[3:], []),
            ("with a gap in front of it", arrived[:1] + arrived[2:], ["north: 1 of 2 numbers are missing, the first is 2"]),
        ):
            with self.subTest(what):
                self.assertEqual(self.judged(these, story.closing(at))[1], said)
        # At the very moment it was asked it is not before any more.
        self.assertEqual(story.closing(at + 1)["numbers"], {"north": 3})
        self.assertEqual(self.judged(arrived, story.closing(at + 1) | {"numbers": {"north": 2}})[1], ["north: 1 numbers above the announced 2 were received before the closing"])

    def test_03_a_line_is_doubled(self):
        for place in range(12):
            for later in (1, 100):
                story = self.three()
                arrived = deliver(story)
                arrived.insert(place + later, arrived[place])
                with self.subTest(place=place, later=later):
                    self.right(story, arrived)

    def test_04_a_spoiled_copy_comes_first(self):
        story = self.three()
        arrived = deliver(story)
        arrived.insert(0, Delivery(5, False, feed.spoiled(story.sent[5], story.chance)))
        self.right(story, arrived)

    def test_04_a_spoiled_copy_comes_instead(self):
        story = self.three()
        arrived = deliver(story)
        arrived[1] = Delivery(1, False, feed.spoiled(story.sent[1], story.chance))
        self.right(story, arrived, ["north: 1 of 4 numbers are missing, the first is 2"])

    def test_05_another_body_under_the_same_id(self):
        for reverse in (False, True):
            story = Story()
            first = story.order(cents=100)
            story.contradicted(first, body("N-other", first.placed_us, 999_999))
            story.contradicted(first, b"nothing")
            story.again(first)
            arrived = deliver(story)
            with self.subTest(reverse=reverse):
                self.right(story, arrived[::-1] if reverse else arrived)

    def test_05_what_comes_after_another_body_is_compared_with_the_first(self):
        story = Story()
        first = story.order(cents=100)
        story.again(first)
        story.contradicted(first, body("N-other", first.placed_us, 999_999))
        story.again(first)
        # The other body once more. It is not the first one either.
        story.contradicted(first, body("N-other", first.placed_us, 999_999))
        story.contradicted(first, body("N-third", first.placed_us, 1))
        self.right(story)

    def test_05_another_body_under_the_id_of_something_unreadable(self):
        story = Story()
        first = story.unreadable("north", "not an object", b"[]")
        story.contradicted(first, body("N-1", moment("north", "2027-03-10T12:00:00")))
        self.right(story)

    def test_05_the_same_id_on_another_feed_is_another_event(self):
        story = Story()
        story.order(event_id="evt_x")
        story.order(event_id="evt_x", feed="north-phone")
        story.order("plaza", event_id="evt_x")
        self.right(story)

    def test_05_ids_in_other_letters_are_other_ids(self):
        story = Story()
        for event_id in ("evt_a", "evt_A", "EVT_a", "evt:a", "evt-a"):
            story.order(event_id=event_id)
        self.right(story)

    def test_23_two_lines_with_one_number(self):
        """Both fingerprints fit. Nobody can say which one is right, so nothing is guessed, and what stands behind it waits."""
        for more in (1, 2):
            story = self.three()
            others = [feed.line("north", 2, "north-web", f"evt_other_{number}", story.sent[1].received_us, story.sent[1].body) for number in range(more)]
            # A copy of one that contradicts another is no duplicate of anything.
            copies = [story.sent[1].line, others[0]]
            rows, problems = self.judged([*deliver(story), *(Delivery(1, True, line) for line in [*others, *copies])])
            self.assertEqual(problems, [f"north: {more + 1} different lines have the number 2"])
            self.assertEqual([row.reason for row in rows if (row.shop, row.n) == ("north", 2)], ["contradicts"] * (1 + more + 2))
            for closing in (None, story.closing()):
                rows, problems = self.judged([*deliver(story), *(Delivery(1, True, line) for line in others)], closing)
                with self.subTest(more=more, closing=closing):
                    self.assertEqual(problems, [f"north: {more + 1} different lines have the number 2"])
                    said = [(row.n, row.verdict, row.reason) for row in rows if row.shop == "north"]
                    self.assertEqual(said, [(1, "valid", "an order"), (2, "bad", "contradicts"), *((n, "waiting", "behind a contradiction") for n in (3, 4)), *[(2, "bad", "contradicts")] * more])
                    self.assertEqual({row.verdict for row in rows if row.shop != "north"}, {"valid"})

    def test_23_a_contradiction_behind_a_missing_number(self):
        story = self.three()
        other = feed.line("north", 3, "north-web", "evt_other", story.sent[2].received_us, story.sent[2].body)
        rows, problems = self.judged([*deliver(story, dropped={1}), Delivery(2, True, other)], story.closing())
        self.assertEqual(problems, ["north: 1 of 4 numbers are missing, the first is 2", "north: 2 different lines have the number 3"])
        self.assertEqual([(row.n, row.reason) for row in rows if row.shop == "north"], [(1, "an order"), (3, "contradicts"), (4, "behind a missing number"), (3, "contradicts")])

    def test_23_what_stands_behind_a_contradiction_is_not_judged_without_it(self):
        story = Story()
        story.order(number="N-1", cents=100)
        story.order(number="N-1", cents=1, verdict="bad", reason="number used")
        other = feed.line("north", 1, "north-web", "evt_other", story.sent[0].received_us, body("N-9", story.sent[0].placed_us, 100))
        rows, _ = self.judged([*deliver(story), Delivery(0, True, other)])
        self.assertEqual([(row.verdict, row.reason) for row in rows], [("bad", "contradicts"), ("waiting", "behind a contradiction"), ("bad", "contradicts")])

    def test_24_a_feed_belongs_to_one_shop(self):
        """If one does not, the run is red. But no shop is judged by what another one has sent."""
        story = Story()
        # The numbers of the two are different, so that all engines mean the same by the first of them.
        story.order("plaza")
        story.order("north", feed="web", event_id="evt_1", number="N-1")
        story.again(story.order("plaza", feed="web", event_id="evt_1", number="N-1"))
        self.right(story, problems=["web is a feed of north and plaza"])

    def test_05_the_lower_number_counts_even_if_it_was_received_later(self):
        for seconds in (5, -5):
            story = Story()
            first = story.order(received="2027-03-10T13:00:00", cents=100)
            story.contradicted(first, body("N-other", first.placed_us, 999_999), seconds)
            story.order(received="2027-03-10T12:59:00", number=json.loads(first.body)["order"], verdict="bad", reason="number used")
            with self.subTest(seconds=seconds):
                self.right(story)

    def test_06_two_copies_of_something_unreadable(self):
        story = Story()
        first = story.unreadable("north", "not an object", b"[]")
        story.again(first)
        arrived = deliver(story)
        self.right(story, [*arrived, arrived[0]])

    def test_07_any_order_of_arrival(self):
        for seed in range(30):
            story = self.three(seed)
            story.contradicted(story.sent[0], body("N-x", story.sent[0].placed_us))
            story.again(story.sent[4])
            arrived = deliver(story, doubled=0.3, broken=0.2, shuffled=True)
            with self.subTest(seed=seed):
                self.right(story, arrived)

    def test_08_out_of_order(self):
        story = Story()
        story.order(placed="2027-03-10T12:05:00")
        story.order(placed="2027-03-10T12:00:00", received="2027-03-10T12:06:00")
        story.order(placed="2027-03-10T12:05:00", received="2027-03-10T12:06:00")
        story.order("plaza", placed="2027-03-10T09:00:00")
        story.order(placed="2027-03-10T12:00:10", received="2027-03-10T12:06:00")
        # Later than the one right before it, and still not in order.
        story.order(placed="2027-03-10T12:00:30", received="2027-03-10T12:06:00")
        story.order(placed="2027-03-10T12:05:01")
        # It came on another channel, but it is the same shop.
        story.order(placed="2027-03-10T12:05:00", received="2027-03-10T12:07:00", feed="north-phone")
        arrived = deliver(story)
        for what, these in (("as it happened", arrived), ("backwards", arrived[::-1]), ("turned", arrived[3:] + arrived[:3])):
            with self.subTest(what):
                rows = {(row.shop, row.n): row.out_of_order for row in self.right(story, these)}
                self.assertEqual([rows["north", n] for n in range(1, 8)], [0, 1, 0, 1, 1, 0, 1])

    def test_08_what_is_not_valid_makes_nobody_late(self):
        story = Story()
        story.order(placed="2027-03-10T12:30:00", received="2027-03-10T12:00:00", verdict="bad", reason="from the future")
        story.order(placed="2027-03-10T12:00:00")
        self.assertEqual([row.out_of_order for row in self.right(story)], [0, 0])

    def test_09_when_a_day_is_closed(self):
        for shop in SHOPS:
            story = Story()
            placed = "2027-03-10T23:59:59"
            story.order(shop, placed, "2027-03-11T05:59:59.999999")
            story.order(shop, placed, "2027-03-11T06:00:00", late=1)
            story.order(shop, placed, "2027-03-12T23:59:59", late=1)
            # The next day has begun, and is closed a day later.
            story.order(shop, "2027-03-11T00:00:00", "2027-03-12T05:59:59.999999")
            story.order(shop, "2027-03-11T00:00:00", "2027-03-12T06:00:00", late=1)
            with self.subTest(shop):
                self.right(story)

    def test_10_two_days_come_at_once(self):
        """Late is decided by when webhook-platform received it. So what came in time there is not late here."""
        story = Story()
        for minute in range(10):
            story.order(placed=f"2027-03-10T12:{minute:02}:00", feed="north-phone")
        for minute in range(10):
            story.order(placed=f"2027-03-12T12:{minute:02}:00")
        arrived = deliver(story)
        self.right(story, arrived[10:] + arrived[:10])

    def test_11_too_old_and_from_the_future(self):
        story = Story()
        oldest, newest = LIMITS["oldest_days"], LIMITS["future_minutes"]
        self.assertEqual((oldest, newest), (35, 5))
        # 35 days before 14 April, 12 o'clock in London is 10 March, 11 o'clock: the clock was changed in between.
        story.order(placed="2027-03-10T11:00:00", received="2027-04-14T12:00:00", late=1)
        story.order(placed="2027-03-10T11:00:00", received="2027-04-14T12:00:00.000001", verdict="bad", reason="too old")
        story.order(placed="2027-03-10T10:59:59", received="2027-04-14T12:00:00", verdict="bad", reason="too old")
        story.order(placed="2027-03-10T12:05:00", received="2027-03-10T12:00:00")
        story.order(placed="2027-03-10T12:05:00", received="2027-03-10T11:59:59.999999", verdict="bad", reason="from the future")
        story.order(placed="2027-03-10T12:05:01", received="2027-03-10T12:00:00", verdict="bad", reason="from the future")
        self.right(story)

    def test_11_an_order_of_weeks_ago_comes_alone(self):
        story = Story()
        story.order(placed="2027-03-10T12:00:00", received="2027-04-10T12:00:00", late=1)
        self.right(story)
        # The same when no day is being closed.
        self.assertEqual(self.judged(deliver(story))[0][0].verdict, "valid")

    def test_11_alone_at_the_limits(self):
        """Nothing else is there that could bring the day of this order with it."""
        for what, placed, received in (("35 days", "2027-03-10T11:00:00", "2027-04-14T12:00:00"), ("5 minutes ahead", "2027-03-11T00:04:00", "2027-03-10T23:59:00")):
            story = Story()
            story.order(placed=placed, received=received, late=int(what == "35 days"))
            with self.subTest(what):
                self.right(story)
                # The same when no day is being closed.
                self.assertEqual(self.judged(deliver(story))[0][0].verdict, "valid")

    def test_11_any_moment_that_can_be_written(self):
        """Whatever a shop writes there, it is one line's problem and nobody else's."""
        story = Story()
        story.order()
        for placed, reason in (("0001-01-01T00:00:00Z", "too old"), ("1969-12-31T23:59:59Z", "too old"), ("9999-12-31T23:59:59Z", "from the future")):
            story.event("north", moment("north", "2027-03-10T12:00:00"), body(f"N-{placed[:4]}", 0, placed_at=placed), verdict="bad", reason=reason)
        us = feed.micros("2000-01-01T00:00:00")
        story.event("north", us, body("N-2000", us), verdict="bad", reason="no day for this shop")
        us = feed.micros("2199-12-31T23:59:59")
        story.event("north", us, body("N-2199", us), placed_us=us, day="2199-12-31", cents=1250)
        story.order()
        rows, problems = self.judged(deliver(story), story.closing())
        self.assertEqual((count.differences(story, deliver(story), rows, problems), problems), ([], []))

    def test_12_a_day_with_23_hours(self):
        story = Story()
        for local, day in (("2027-03-27T23:59:59", "2027-03-27"), ("2027-03-28T00:00:00", "2027-03-28"), ("2027-03-28T00:59:59", "2027-03-28"), ("2027-03-28T02:00:00", "2027-03-28"), ("2027-03-28T23:59:59", "2027-03-28"), ("2027-03-29T00:00:00", "2027-03-29"), ("2027-03-29T00:30:00", "2027-03-29")):
            self.assertEqual(story.order(placed=local).day, day)
        self.right(story)
        # The same, as the hand-over writes it.
        self.assertIn(b"2027-03-28T22:59:59Z", story.sent[4].body)
        self.assertIn(b"2027-03-28T23:00:00Z", story.sent[5].body)

    def test_13_a_day_with_25_hours(self):
        for shop, day in (("north", "2026-10-25"), ("plaza", "2026-10-25"), ("harbour", "2026-11-01")):
            story = Story()
            for local in ("00:00:00", "01:30:00", "02:30:00", "03:30:00", "23:59:59"):
                story.order(shop, f"{day}T{local}")
            # The hour that stands twice on the clock, the second time.
            twice = {"north": "01:30:00", "plaza": "02:30:00", "harbour": "01:30:00"}[shop]
            placed_us = moment(shop, f"{day}T{twice}") + 3_600_000_000
            story.event(shop, placed_us + 2_000_000, body("N-twice", placed_us, 5), placed_us=placed_us, day=day, cents=5)
            with self.subTest(shop):
                self.right(story)

    def test_13_each_shop_has_its_own_day(self):
        story = Story()
        for shop in SHOPS:
            story.order(shop, "2027-03-20T23:59:59")
            story.order(shop, "2027-03-21T00:00:00")
        # In these two weeks New York is four hours behind London, and not five.
        self.assertEqual((moment("harbour", "2027-03-21T00:00:00") - moment("north", "2027-03-21T00:00:00")) // 3_600_000_000, 4)
        self.right(story)

    def test_13_a_shop_without_a_clock(self):
        """Its orders would be bad in silence. So the run is red, until somebody says which clock it has."""
        story = Story()
        story.order("plaza", verdict="bad", reason="no day for this shop")
        shops = {name: zones for name, zones in SHOPS.items() if name != "plaza"}
        self.right(story, shops=shops, problems=["plaza has no clock"])
        # It is enough that something is announced of it.
        closing = {"at_us": moment("north", "2027-03-10T12:00:00"), "numbers": {"plaza": 2}}
        self.assertEqual(self.judged([], closing, shops)[1], ["plaza has no clock", "plaza: 2 of 2 numbers are missing, the first is 1"])
        self.assertEqual(self.judged([], closing | {"numbers": {"plaza": 0}}, shops)[1], [])

    def test_13_an_order_before_a_shop_is_there(self):
        story = Story()
        story.order("plaza", "2027-03-09T23:59:59", "2027-03-10T00:00:01", verdict="bad", reason="no day for this shop")
        story.order("plaza", "2027-03-10T00:00:00", "2027-03-09T23:59:00")
        self.right(story, shops=SHOPS | {"plaza": [["2027-03-10", "Europe/Madrid"]]})

    def test_15_a_field_that_nobody_knows_from_the_middle_of_a_day_on(self):
        story = Story()
        for number in range(6):
            story.order(placed=f"2027-03-10T12:0{number}:00", more=[] if number < 3 else [("note", "x")], cents=0 if number == 4 else 1250)
        self.assertEqual([row.more for row in self.right(story)], [0, 0, 0, 1, 1, 1])

    def test_16_a_field_gets_another_name_from_the_middle_of_a_day_on(self):
        story = Story()
        for number in range(6):
            if number < 3:
                story.order(placed=f"2027-03-10T12:0{number}:00")
            else:
                story.unreadable("north", "missing or wrong: cents", body(f"N-{number}", moment("north", "2027-03-10T12:00:00"), without=("cents",), more=[("amount", 1250)]))
        self.right(story)

    def test_17_every_body_gets_the_answer_of_webhook_platform(self):
        with open(ROOT / "examples" / "bodies.jsonl", encoding="utf-8") as file:
            examples = [json.loads(text) for text in file]
        for seed in range(3):
            story = Story(seed)
            for at, example in enumerate(examples):
                of_it, received_us = base64.b64decode(example["body"]), moment("north", "2026-11-24T10:00:00")
                if example["says"] != "order":
                    story.event("north", received_us, of_it, verdict="bad", reason=example["says"])
                    continue
                # Read in the easy way, which is good enough for what is known to be an order. Many of them have the same number, so
                # each comes on a channel of its own.
                plain = json.loads(of_it.decode("utf-8", "replace"))
                placed_us = feed.micros(plain["placed_at"].rstrip("Z"))
                story.event(
                    "north", max(received_us, placed_us), of_it, feed=f"north-{at}", placed_us=placed_us, day=plain["placed_at"][:10],
                    cents=plain["cents"], more=int(len(plain) > 6),
                )
            with self.subTest(seed=seed):
                self.right(story, deliver(story, shuffled=True))

    def test_20_the_same_number_on_two_channels(self):
        story = Story()
        story.order(number="N-1", feed="north-web", cents=1)
        story.order(number="N-1", feed="north-phone", cents=2)
        story.order("plaza", number="N-1", cents=3)
        story.order(number="N-1", feed="north-web", cents=4, verdict="bad", reason="number used")
        story.order(number="N-1", feed="north-web", cents=5, verdict="bad", reason="number used")
        story.order(number="n-1", feed="north-web", cents=6)
        self.right(story)

    def test_20_a_number_is_used_even_if_its_order_is_too_old(self):
        story = Story()
        story.order(placed="2027-02-01T12:00:00", received="2027-03-10T12:00:00", number="N-1", verdict="bad", reason="too old")
        story.order(number="N-1", verdict="bad", reason="number used")
        story.order(placed="2027-03-10T13:00:00", received="2027-03-10T12:00:00", number="N-2", verdict="bad", reason="from the future")
        story.order(number="N-2", verdict="bad", reason="number used")
        self.right(story)

    def test_20_of_several_reasons_the_first_one_counts(self):
        story = Story()
        story.order(number="N-1")
        story.order(number="N-1", placed="2027-02-01T12:00:00", received="2027-03-10T12:00:00", verdict="bad", reason="too old")
        story.order(number="N-1", placed="2027-03-10T13:00:00", received="2027-03-10T12:00:00", verdict="bad", reason="from the future")
        first = story.unreadable("north", "not an object", b"[]")
        story.contradicted(first, b"null")
        story.contradicted(story.sent[0], body("N-1", moment("north", "2027-02-01T12:00:00")))
        self.right(story)
        # Without a clock its number does not matter any more.
        story = Story()
        for _ in range(2):
            story.order(number="N-1", verdict="bad", reason="no day for this shop")
        self.right(story, shops=SHOPS | {"north": [["2027-06-01", "Europe/London"]]})

    def test_20_what_is_unreadable_or_another_body_uses_no_number(self):
        story = Story()
        story.unreadable("north", "missing or wrong: cents", body("N-1", moment("north", "2027-03-10T12:00:00"), without=("cents",)))
        first = story.order(number="N-2")
        story.contradicted(first, body("N-1", first.placed_us))
        story.order(number="N-1")
        self.right(story)


if __name__ == "__main__":
    import unittest

    unittest.main()
