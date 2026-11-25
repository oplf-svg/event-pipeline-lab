"""Everything at once, in any order, in any batches, over several runs, and counted from outside."""

import os
import tempfile

from lab import LIMITS, SHOPS, Lab, count, engine, feed, run

from pipeline import store

SIZE = int(os.environ.get("STORM_LINES", 400))
TIMES = int(os.environ.get("STORM_TIMES", 6))
KINDS = [(engine.Sqlite, store.Plain)] + ([(engine.Duck, store.Parquet)] if len(engine.all_of_them()) > 1 else [])


class Storm(Lab):
    def seeds(self):
        return [int.from_bytes(os.urandom(4)) for _ in range(TIMES)]

    def test_any_number_of_batches_and_runs(self):
        for seed in self.seeds():
            for engine_of, store_of in KINDS:
                with self.subTest(seed=seed, engine=engine_of.name), tempfile.TemporaryDirectory() as folder:
                    story = feed.everything(seed, SIZE)
                    arrived, chance = feed.deliver(story, doubled=0.15, broken=0.08, shuffled=True), story.chance
                    pipeline = run.Pipeline(folder, SHOPS, LIMITS, engine_of, store_of)
                    at, said = 0, {}
                    while at < len(arrived):
                        size = chance.choice([0, 1, 7, 50, 200])
                        pipeline.take([delivery.line for delivery in arrived[at : at + size]])
                        at += size
                        if chance.random() < 0.4:
                            self.never_changes(said, pipeline.run().rows)
                    last = pipeline.run(story.closing())
                    self.never_changes(said, last.rows)
                    self.assertEqual(count.differences(story, arrived, last.rows, last.problems), [])
                    counted = {name: counter for name, counter in last.counts.items() if name != "reasons"}
                    self.assertEqual(counted, dict(sorted(count.sums(story, arrived).items())))

    def test_what_is_lost_is_red_until_it_is_sent_again(self):
        for seed in self.seeds():
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as folder:
                story = feed.everything(seed, SIZE)
                lost = set(story.chance.sample(range(len(story.sent)), 5))
                arrived = feed.deliver(story, doubled=0.1, dropped=lost, shuffled=True)
                pipeline = run.Pipeline(folder, SHOPS, LIMITS)
                pipeline.take([delivery.line for delivery in arrived])
                red = pipeline.run(story.closing())
                self.assertEqual(count.differences(story, arrived, red.rows, [], []), [])
                wanted = {}
                for place in lost:
                    sent = story.sent[place]
                    wanted.setdefault(sent.shop, []).append(sent.n)
                lines = [f"{shop}: {len(numbers)} of {story.last[shop]} numbers are missing, the first is {min(numbers)}" for shop, numbers in wanted.items()]
                self.assertEqual(red.problems, sorted(lines))
                again = [feed.Delivery(place, True, story.sent[place].line) for place in sorted(lost)]
                pipeline.take([delivery.line for delivery in again])
                green = pipeline.run(story.closing())
                self.assertEqual(count.differences(story, arrived + again, green.rows, green.problems), [])

    def test_closings_in_between(self):
        """Each is asked while some of what was received later is there already, and something comes twice or spoiled."""
        shops = {name: [["2027-03-08", zones[0][1]]] for name, zones in SHOPS.items()}
        asked = [feed.moment(shop, f"2027-03-{day}T06:00:00") for day in (12, 17, 24) for shop in SHOPS]
        for seed in self.seeds():
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as folder:
                story = feed.everything(seed, SIZE, opened="2027-03-08", asked=sorted(asked))
                arrived, chance = feed.deliver(story, doubled=0.1, broken=0.05), story.chance
                pipeline, taken, said, waits = run.Pipeline(folder, shops, LIMITS), [], {}, arrived
                for at in [*sorted(asked), None]:
                    closing = story.closing(at)
                    announced = {place for place, sent in enumerate(story.sent) if sent.n <= closing["numbers"].get(sent.shop, 0)}
                    now = [one for one in waits if one.place_in_story in announced or chance.random() < 0.1]
                    # Two copies of a line are equal, and still two.
                    these = {id(one) for one in now}
                    waits = [one for one in waits if id(one) not in these]
                    chance.shuffle(now)
                    taken += now
                    pipeline.take([one.line for one in now])
                    done = pipeline.run(closing)
                    self.never_changes(said, done.rows)
                    self.assertEqual(count.differences(story, taken, done.rows, done.problems), [])

    def test_the_same_whatever_the_order(self):
        story = feed.everything(self.seeds()[0], SIZE)
        seen = set()
        for _ in range(5):
            rows, problems = self.judged(feed.deliver(story, doubled=0.1, shuffled=True), story.closing())
            self.assertEqual(problems, [])
            seen.add(tuple(sorted(row[1:] for row in rows if row.reason != "the same line")))
        self.assertEqual(len(seen), 1)

    def never_changes(self, said, rows):
        """Whatever was said of a number once stays, but that it waits."""
        for row in rows:
            if row.n is not None and row.verdict != "waiting" and row.reason != "the same line":
                self.assertEqual(said.setdefault((row.shop, row.n), row[3:]), row[3:], f"{row.shop} {row.n}")


if __name__ == "__main__":
    import unittest

    unittest.main()
