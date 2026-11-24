"""The strict reader: the bodies that webhook-platform and this pipeline share, and that nothing else can come out of it."""

import os
import unittest

import looks
import make_bodies


class Reader(unittest.TestCase):
    def setUp(self):
        self.reader = looks.load(looks.READER)

    def test_every_body_gets_its_answer(self):
        for example in looks.examples():
            with self.subTest(example.name):
                self.assertEqual(looks.says(self.reader, example.body), example.says)

    def test_an_order_holds_what_stood_in_it(self):
        self.assertEqual(looks.wrong_values(self.reader), {})

    def test_the_deepest_body_there_can_be(self):
        self.assertEqual(looks.wrong_at_the_limit(self.reader), {})

    def test_nothing_else_can_come_out_of_it(self):
        seed = int.from_bytes(os.urandom(4))
        self.assertEqual(looks.strange_answers(self.reader, seed, 30_000), {}, f"seed {seed}")

    def test_every_reason_has_a_body(self):
        self.assertEqual({example.says for example in looks.examples()}, looks.REASONS | {"order"})

    def test_each_body_has_a_name_of_its_own(self):
        names = [example.name for example in looks.examples()]
        self.assertEqual(len(names), len(set(names)))

    def test_the_file_is_what_the_program_writes(self):
        self.assertEqual(make_bodies.FILE.read_text(encoding="utf-8"), "".join(make_bodies.lines()))


if __name__ == "__main__":
    unittest.main()
