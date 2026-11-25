"""What the tests of the pipeline have in common."""

import importlib.util
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from outside import count, feed  # noqa: E402
from pipeline import engine, run  # noqa: E402

SHOPS, LIMITS = run.settings()
# The stories are of 2027. For them all of it has been.
NOW_US = run.now_us
run.now_us = lambda: feed.micros("2199-12-31T23:59:59")
ENGINES = engine.all_of_them()


class Lab(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if os.environ.get("EVERY_ENGINE"):
            assert [one.name for one in ENGINES] == ["sqlite", "duckdb"], "an engine is missing"
            assert importlib.util.find_spec("tzdata"), "the pinned list of clock rules is missing"

    def judged(self, deliveries, closing=None, shops=SHOPS):
        """What every engine says of it. They have to say the same."""
        came = list(run.arrived([delivery.line for delivery in deliveries]))
        said = [run.judge(came, shops, LIMITS, one) for one in ENGINES]
        for other in said[1:]:
            self.assertEqual(said[0], other, "the engines disagree")
        return said[0], run.problems(came, said[0], shops, closing)

    def right(self, story, deliveries=None, problems=(), shops=SHOPS):
        """Each line got the verdict that it has to have, and the sums are right."""
        deliveries = feed.deliver(story) if deliveries is None else deliveries
        rows, found = self.judged(deliveries, story.closing(), shops)
        self.assertEqual(count.differences(story, deliveries, rows, found, problems), [])
        if not problems:
            counted = run.count(rows)
            counted.pop("reasons")
            self.assertEqual(counted, dict(sorted(count.sums(story, deliveries).items())))
        return rows
