"""Proves that the tests of the rules, the days, the lines and the files can fail: one mistake at a time, in a copy.

Each mistake names the tests that have to notice it, every time. A mistake that does not even run proves nothing, and does not count.

    python wrong_rules.py           all of them
    python wrong_rules.py 2/4       the second of four parts
    python wrong_rules.py NAME...   only these
"""

import concurrent.futures
import dataclasses
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARTS = ("pipeline", "rules", "outside", "tests", "examples", ".github/scripts")
# Runs some tests, and says of each whether it failed or broke, and how.
RUNNER = """
import json, sys, unittest
sys.path.insert(0, "tests")
result = unittest.TestResult()
unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]).run(result)
def named(found):
    return [[getattr(test, "test_case", test).id(), text.strip()[-3000:]] for test, text in found]
print(json.dumps({"run": result.testsRun, "failed": named(result.failures), "broke": named(result.errors)}))
"""
# At the beginning of a line, where Python says what it was. Some messages go on behind it.
NOT_EVEN_RUN = re.compile(r"^[\w.]*(SyntaxError|NameError|ImportError|ModuleNotFoundError|IndentationError|OperationalError|UnboundLocalError|BinderException|ParserException|CatalogException)\b", re.MULTILINE)


@dataclasses.dataclass(frozen=True)
class Wrong:
    name: str
    what: str
    noticed_by: tuple[str, ...]
    file: str
    changes: tuple[tuple[str, str], ...]

    def put_into(self, text):
        for old, new in self.changes:
            if text.count(old) != 1:
                raise ValueError(f"{self.name}: stands {text.count(old)} times in {self.file}: {old}")
            text = text.replace(old, new)
        return text


CLASSES = {"rows": "test_rows.Rows", "raw": "test_raw.Files", "days": "test_days.Days", "line": "test_line.Lines", "rules": "test_rules.Rules", "storm": "test_storm.Storm", "hold": "test_hold.Hold"}


def wrong(file, name, what, noticed_by, *changes):
    """Who notices it: a test of one row of the contract, or "raw:..." for one of the files, and so on."""
    words = [word.rpartition(":") for word in noticed_by.split()]
    return Wrong(name, what, tuple(f"{CLASSES[where or 'rows']}.test_{test}" for where, _, test in words), file, changes)


LINES, VALID, MARKS, VERDICTS = "rules/lines.sql", "rules/valid.sql", "rules/marks.sql", "rules/verdicts.sql"
DAYS, LINE, RUN, STORE, ENGINE, COUNT = "pipeline/days.py", "pipeline/line.py", "pipeline/run.py", "pipeline/store.py", "pipeline/engine.py", "outside/count.py"
TESTS = ".github/scripts/tests.sh"
NUMBER_RANK = "row_number() over (partition by shop order by n) as rank_of_n"
OF_ID = "row_number() over (partition by j.shop, j.event_print order by j.n) as of_its_id"
FIRST_BODY = "first_value(j.body_print) over (partition by j.shop, j.event_print order by j.n) as first_body"
OF_NUMBER = "row_number() over (partition by shop, order_print order by n) as of_its_number"
DAY_JOIN = "left join shop_days d on d.shop = e.shop and e.placed_us >= d.from_us and e.placed_us < d.to_us"
NEWEST = "over (\n                   partition by a.shop order by a.n rows between unbounded preceding and 1 preceding)"
LATE_ORDER = "            when o.of_its_number > 1                              then 'number used'\n"
NO_DAY = "            when d.shop_day is null                               then 'no day for this shop'\n"
PRINTS = 'event_print, order_print = (_print(f"{found.feed} {name}".encode()) for name in (found.event_id, order.get("order")))'
SAID = "        if tuple(row[1:]) != wanted:\n"


def blind(at, what):
    """The counter outside does not look at one value."""
    return wrong(COUNT, f"count.{what}", f"The counter does not look at {what.replace('_', ' ')}", "00_the_counter_sees_every_difference", (SAID, f"        row = (*row[:{at + 1}], wanted[{at}], *row[{at + 2}:])\n{SAID}"))


EVERY_ONE = [
    # Which line stands for its number.
    wrong(LINES, "lines.by_arrival", "Numbers are ranked by arrival", "07_any_order_of_arrival storm:any_number_of_batches_and_runs", (NUMBER_RANK, NUMBER_RANK.replace("order by n", "order by place"))),
    wrong(LINES, "lines.all_shops", "One row of numbers for all shops", "07_any_order_of_arrival 02_a_line_is_dropped_and_sent_again", (NUMBER_RANK, NUMBER_RANK.replace("partition by shop order by n", "order by n, shop"))),
    wrong(LINES, "lines.never_waits", "What stands behind a missing number is judged", "02_a_line_is_dropped storm:what_is_lost_is_red_until_it_is_sent_again raw:07_what_waits_may_change_and_nothing_else", ("            when i.n <> i.rank_of_n       then 'behind a missing number'\n", "")),
    wrong(LINES, "lines.one_gap", "One missing number does not matter", "02_a_line_is_dropped", ("when i.n <> i.rank_of_n ", "when i.n > i.rank_of_n + 1 ")),
    wrong(LINES, "lines.copies_stand", "A copy is judged like the line itself", "03_a_line_is_doubled", ("            when a.place <> i.place       then 'the same line'\n", "")),
    wrong(LINES, "lines.last_copy", "The last copy stands for its number", "03_a_line_is_doubled", ("min(place) as place", "max(place) as place")),
    wrong(LINES, "lines.copies_wait", "A copy behind a missing number waits", "raw:07_what_waits_may_change_and_nothing_else", ("            when a.place <> i.place       then 'the same line'\n            when i.n <> i.rank_of_n       then 'behind a missing number'\n", "            when i.n <> i.rank_of_n       then 'behind a missing number'\n            when a.place <> i.place       then 'the same line'\n")),
    wrong(LINES, "lines.copies_contradict", "Two copies of one line contradict each other", "03_a_line_is_doubled", ("count(distinct line_print)", "count(line_print)")),
    wrong(LINES, "lines.copy_first", "A copy of a line that contradicts another is a duplicate", "23_two_lines_with_one_number", ("            when i.different_lines > 1    then 'contradicts'\n            when a.place <> i.place       then 'the same line'\n", "            when exists (select 1 from arrived o where o.line_print = a.line_print and o.place < a.place) then 'the same line'\n            when i.different_lines > 1    then 'contradicts'\n")),
    wrong(LINES, "lines.contradiction", "Of two different lines with one number the first one is right", "23_two_lines_with_one_number", ("            when i.different_lines > 1    then 'contradicts'\n", "")),
    wrong(LINES, "lines.of_three", "Of three different lines with one number the first one is right", "23_two_lines_with_one_number", ("i.different_lines > 1 ", "i.different_lines = 2 ")),
    wrong(LINES, "lines.contradiction_waits", "A contradiction behind a missing number waits", "23_a_contradiction_behind_a_missing_number", ("when i.different_lines > 1    then", "when i.different_lines > 1 and i.n = i.rank_of_n then")),
    wrong(LINES, "lines.goes_on", "What stands behind a contradiction is judged without it", "23_two_lines_with_one_number 23_what_stands_behind_a_contradiction_is_not_judged_without_it", ("            when i.most_lines > 1         then 'behind a contradiction'\n", "")),
    wrong(LINES, "lines.only_behind", "Only the number right behind a contradiction waits", "23_two_lines_with_one_number", ("rows between unbounded preceding and current row", "rows between 1 preceding and current row")),
    wrong(LINES, "lines.all_shops_wait", "A contradiction stops all shops", "23_two_lines_with_one_number", ("max(different_lines) over (partition by shop order by n", "max(different_lines) over (order by n, shop")),
    wrong(LINES, "lines.spoiled_waits", "What is spoiled waits", "01_one_bit_is_flipped 04_a_spoiled_copy_comes_first", ("when a.spoiled = 1            then 'spoiled'", "when a.spoiled = 1            then 'behind a missing number'")),
    # What a valid order is.
    wrong(VALID, "valid.same_is_bad", "The same event once more is bad", "06_two_copies_of_something_unreadable", ("case when e.of_its_id > 1 and e.body_print = e.first_body  then 'the same event'", "case when e.of_its_id > 1 and e.body_print = e.first_body  then 'another body'")),
    wrong(VALID, "valid.other_body_is_same", "Nobody looks at the body of a known id", "05_another_body_under_the_same_id", ("when e.of_its_id > 1 and e.body_print = e.first_body ", "when e.of_its_id > 1 ")),
    wrong(VALID, "valid.same_counts", "The same event once more is an order", "06_two_copies_of_something_unreadable 05_another_body_under_the_same_id", ("then 'the same event'\n            when e.of_its_id > 1 ", "then null\n            when e.of_its_id > 1 ")),
    wrong(VALID, "valid.last_wins", "The last body of an id counts", "05_another_body_under_the_same_id", (OF_ID, OF_ID.replace("order by j.n", "order by j.n desc")), (FIRST_BODY, FIRST_BODY.replace("order by j.n", "order by j.n desc"))),
    wrong(VALID, "valid.received_first", "The body of an id counts that was received first", "05_the_lower_number_counts_even_if_it_was_received_later", (OF_ID, OF_ID.replace("order by j.n", "order by j.received_us, j.n")), (FIRST_BODY, FIRST_BODY.replace("order by j.n", "order by j.received_us, j.n"))),
    wrong(VALID, "valid.compares_with_last", "A body is compared with the last one of its id", "05_what_comes_after_another_body_is_compared_with_the_first", (FIRST_BODY, FIRST_BODY.replace("order by j.n", "order by j.n desc"))),
    wrong(VALID, "valid.compares_with_any", "A body is compared with the one before it", "05_what_comes_after_another_body_is_compared_with_the_first", (FIRST_BODY, "max(j.body_print) over (partition by j.shop, j.event_print order by j.n rows between 1 preceding and 1 preceding) as first_body")),
    wrong(VALID, "valid.id_of_orders", "Only orders have ids", "05_another_body_under_the_id_of_something_unreadable", (OF_ID, OF_ID.replace("j.event_print order", "j.event_print, j.says order")), (FIRST_BODY, FIRST_BODY.replace("j.event_print order", "j.event_print, j.says order"))),
    wrong(VALID, "valid.id_of_all", "An id of one shop is one of all shops", "24_a_feed_belongs_to_one_shop", (OF_ID, OF_ID.replace("j.shop, ", ""))),
    wrong(VALID, "valid.body_of_all", "A body is compared with that of another shop", "24_a_feed_belongs_to_one_shop", (FIRST_BODY, FIRST_BODY.replace("j.shop, ", ""))),
    wrong(VALID, "valid.number_of_others", "A number of one shop is one of all shops", "24_a_feed_belongs_to_one_shop", (OF_NUMBER, OF_NUMBER.replace("partition by shop, ", "partition by "))),
    wrong(RUN, "valid.id_of_a_shop", "An id is the same on all channels of a shop", "05_the_same_id_on_another_feed_is_another_event", (PRINTS, PRINTS.replace('f"{found.feed} {name}"', 'f"{found.feed if name == order.get(\'order\') else \'\'} {name}"'))),
    wrong(RUN, "valid.id_letters", "Large and small letters of an id are the same", "05_ids_in_other_letters_are_other_ids", (PRINTS, PRINTS.replace("in (found.event_id,", "in (found.event_id.lower(),"))),
    wrong(VALID, "valid.content_first", "Something unreadable is bad each time it comes", "06_two_copies_of_something_unreadable", ("            when e.says <> 'order'                                then e.says\n", ""), ("case when e.of_its_id > 1 and", "case when e.says <> 'order' then e.says\n            when e.of_its_id > 1 and")),
    wrong(VALID, "valid.unreadable", "Something unreadable is an order", "16_a_field_gets_another_name_from_the_middle_of_a_day_on 17_every_body_gets_the_answer_of_webhook_platform", ("            when e.says <> 'order'                                then e.says\n", "            when e.says <> 'order'                                then null\n")),
    wrong(VALID, "valid.unreadable_why", "Why something is unreadable is not said", "16_a_field_gets_another_name_from_the_middle_of_a_day_on", ("            when e.says <> 'order'                                then e.says\n", "")),
    wrong(RUN, "valid.number_of_a_shop", "A number counts for all channels of a shop", "20_the_same_number_on_two_channels", (PRINTS, PRINTS.replace('f"{found.feed} {name}"', 'f"{found.feed if name == found.event_id else found.shop} {name}"'))),
    wrong(RUN, "valid.number_of_all", "Nobody asks on which channel a number came", "20_the_same_number_on_two_channels", (PRINTS, PRINTS.replace('f"{found.feed} {name}"', 'f"{found.feed if name == found.event_id else \'\'} {name}"')),),
    wrong(RUN, "valid.number_letters", "Large and small letters of a number are the same", "20_the_same_number_on_two_channels", (PRINTS, PRINTS.replace('order.get("order"))', 'order.get("order", "").lower())'))),
    wrong(VALID, "valid.number_twice", "A number may be used twice", "20_the_same_number_on_two_channels", (LATE_ORDER, "")),
    wrong(VALID, "valid.last_number", "Whoever comes last with a number has it", "20_the_same_number_on_two_channels", (OF_NUMBER, OF_NUMBER.replace("order by n", "order by n desc"))),
    wrong(VALID, "valid.other_body_uses_number", "Another body under a known id uses a number", "20_what_is_unreadable_or_another_body_uses_no_number", ("where of_its_id = 1 and says = 'order'", "where says = 'order'")),
    wrong(VALID, "valid.old_uses_no_number", "An order that is too old uses no number", "20_a_number_is_used_even_if_its_order_is_too_old", ("where of_its_id = 1 and says = 'order'", "where of_its_id = 1 and says = 'order' and placed_us >= received_us - 3024000000000")),
    wrong(VALID, "valid.future_uses_no_number", "An order from the future uses no number", "20_a_number_is_used_even_if_its_order_is_too_old", ("where of_its_id = 1 and says = 'order'", "where of_its_id = 1 and says = 'order' and placed_us <= received_us + 300000000")),
    wrong(VALID, "valid.number_first", "The used number is said before anything else", "20_of_several_reasons_the_first_one_counts", (LATE_ORDER, ""), ("            when e.placed_us > e.received_us + x.future_us        then 'from the future'\n", LATE_ORDER + "            when e.placed_us > e.received_us + x.future_us        then 'from the future'\n")),
    wrong(VALID, "valid.number_before_day", "The used number is said before the missing clock", "20_of_several_reasons_the_first_one_counts", (NO_DAY + LATE_ORDER, LATE_ORDER + NO_DAY)),
    wrong(VALID, "valid.future_at_once", "Exactly 5 minutes ahead is too much", "11_too_old_and_from_the_future 11_alone_at_the_limits", ("when e.placed_us > e.received_us", "when e.placed_us >= e.received_us")),
    wrong(VALID, "valid.future_any", "Any future is fine", "11_too_old_and_from_the_future", ("            when e.placed_us > e.received_us + x.future_us        then 'from the future'\n", "")),
    wrong(VALID, "valid.no_future", "Nothing may be a moment ahead", "11_too_old_and_from_the_future", ("e.received_us + x.future_us ", "e.received_us ")),
    wrong(VALID, "valid.old_at_once", "Exactly 35 days is too old", "11_too_old_and_from_the_future 11_alone_at_the_limits", ("when e.placed_us < e.received_us", "when e.placed_us <= e.received_us")),
    wrong(VALID, "valid.old_any", "Any age is fine", "11_too_old_and_from_the_future", ("            when e.placed_us < e.received_us - x.oldest_us        then 'too old'\n", "")),
    wrong(VALID, "valid.day_of_arrival", "An order belongs to the day on which it was received", "09_when_a_day_is_closed", (DAY_JOIN, DAY_JOIN.replace("e.placed_us", "e.received_us"))),
    wrong(VALID, "valid.midnight_twice", "Midnight belongs to both days", "12_a_day_with_23_hours", (DAY_JOIN, DAY_JOIN.replace("< d.to_us", "<= d.to_us"))),
    wrong(VALID, "valid.midnight_never", "Midnight belongs to no day", "12_a_day_with_23_hours", (DAY_JOIN, DAY_JOIN.replace(">= d.from_us", "> d.from_us"))),
    wrong(VALID, "valid.days_of_all", "The days of all shops are the same", "13_each_shop_has_its_own_day", (DAY_JOIN, DAY_JOIN.replace("d.shop = e.shop and ", "d.shop = 'north' and "))),
    wrong(VALID, "valid.every_clock", "An order has a day on every clock", "13_each_shop_has_its_own_day", (DAY_JOIN, DAY_JOIN.replace("d.shop = e.shop and ", ""))),
    wrong(VALID, "valid.no_clock_is_fine", "A shop without a clock has orders", "13_a_shop_without_a_clock", (NO_DAY, "")),
    # The marks.
    wrong(MARKS, "marks.late_after", "At the moment when a day is closed nothing is late", "09_when_a_day_is_closed", ("a.received_us >= v.closes_us", "a.received_us > v.closes_us")),
    wrong(MARKS, "marks.never_late", "Nothing is ever late", "09_when_a_day_is_closed", ("then 1 else 0 end as late", "then 0 else 0 end as late")),
    wrong(MARKS, "marks.late_by_placing", "Late is who ordered late", "09_when_a_day_is_closed", ("a.received_us >= v.closes_us", "a.placed_us >= v.closes_us")),
    wrong(MARKS, "marks.of_the_bad", "What is bad has marks as well", "11_too_old_and_from_the_future 08_what_is_not_valid_makes_nobody_late", ("\n where v.why_not is null", "")),
    wrong(MARKS, "marks.order_of_all", "An order can be out of order because of another shop", "08_out_of_order", (NEWEST, NEWEST.replace("partition by a.shop ", ""))),
    wrong(MARKS, "marks.order_of_channel", "An order is only out of order on its own channel", "08_out_of_order", (NEWEST, NEWEST.replace("partition by a.shop ", "partition by a.shop, a.feed "))),
    wrong(MARKS, "marks.order_by_arrival", "Out of order is who arrived late", "08_out_of_order 10_two_days_come_at_once storm:the_same_whatever_the_order", (NEWEST, NEWEST.replace("order by a.n", "order by a.place"))),
    wrong(MARKS, "marks.order_by_receipt", "Out of order is who was received late", "08_out_of_order", (NEWEST, NEWEST.replace("order by a.n", "order by a.received_us"))),
    wrong(MARKS, "marks.same_moment", "Who ordered at the same moment is out of order", "08_out_of_order", ("when a.placed_us < max(a.placed_us)", "when a.placed_us <= max(a.placed_us)")),
    wrong(MARKS, "marks.only_before", "Only the order right before counts", "08_out_of_order", (NEWEST, NEWEST.replace("unbounded preceding", "1 preceding"))),
    wrong(MARKS, "marks.more_than_one", "One field that nobody knows does not matter", "15_a_field_that_nobody_knows_from_the_middle_of_a_day_on", ("a.more_fields > 0", "a.more_fields > 1")),
    wrong(MARKS, "marks.no_more", "Fields that nobody knows are passed over without a word", "15_a_field_that_nobody_knows_from_the_middle_of_a_day_on", ("when a.more_fields > 0 then 1", "when a.more_fields > 0 then 0")),
    wrong(MARKS, "marks.more_for_money", "Fields that nobody knows only matter if it costs something", "15_a_field_that_nobody_knows_from_the_middle_of_a_day_on", ("when a.more_fields > 0 then 1", "when a.more_fields > 0 and a.cents > 0 then 1")),
    # One verdict for each line.
    wrong(VERDICTS, "verdicts.only_judged", "Only what is judged has a verdict", "01_one_bit_is_flipped 03_a_line_is_doubled", ("left join valid v", "join valid v")),
    wrong(VERDICTS, "verdicts.only_valid", "Only what is valid has a verdict", "05_another_body_under_the_same_id", ("left join marks m", "join marks m")),
    wrong(VERDICTS, "verdicts.waiting_is_bad", "What waits is bad", "02_a_line_is_dropped", ("('behind a missing number', 'behind a contradiction') then 'waiting'", "('behind a missing number', 'behind a contradiction') then 'bad'")),
    wrong(VERDICTS, "verdicts.behind_is_bad", "What stands behind a contradiction is bad", "23_two_lines_with_one_number", ("('behind a missing number', 'behind a contradiction')", "('behind a missing number')")),
    wrong(VERDICTS, "verdicts.copy_is_bad", "A copy is bad", "03_a_line_is_doubled", ("when l.standing = 'the same line'   then 'duplicate'", "when l.standing = 'the same line'   then 'bad'")),
    wrong(VERDICTS, "verdicts.same_is_bad", "The same event once more is bad", "06_two_copies_of_something_unreadable", ("            when v.why_not = 'the same event'   then 'duplicate'\n", "")),
    wrong(VERDICTS, "verdicts.spoiled_is_valid", "What is spoiled is valid", "01_one_bit_is_flipped", ("when l.standing <> 'stands'         then 'bad'", "when l.standing = 'contradicts'     then 'bad'")),
    wrong(VERDICTS, "verdicts.day_of_the_bad", "What is bad has a day, if another order brings it along", "11_too_old_and_from_the_future 20_the_same_number_on_two_channels", ("case when m.place is null then null else v.shop_day end as shop_day", "v.shop_day")),
    wrong(VERDICTS, "verdicts.all_cents", "The cents of everything are added", "11_too_old_and_from_the_future 20_the_same_number_on_two_channels", ("case when m.place is null then 0 else a.cents end", "coalesce(a.cents, 0)")),
    wrong(VERDICTS, "verdicts.no_reason", "Nobody says why", "16_a_field_gets_another_name_from_the_middle_of_a_day_on", ("coalesce(v.why_not, 'an order')", "'an order'")),
    wrong(VERDICTS, "verdicts.moment", "Nobody says when it was received", "22_what_was_received_after_the_closing_is_for_the_next_one 00_verdicts_that_cannot_be_right", (", a.received_us\n", ", a.placed_us as received_us\n")),
    # Plain SQL.
    wrong(VERDICTS, "plain.ifnull", "A function that only some engines have", "rules:they_are_plain", ("coalesce(m.late, 0)", "ifnull(m.late, 0)")),
    wrong(LINES, "plain.star", "All columns, whatever they are", "rules:they_are_plain", ("select shop, n, place, different_lines,\n", "select numbers.*,\n")),
    wrong(LINES, "plain.equals", "Two signs for one", "rules:they_are_plain", ("where spoiled = 0", "where spoiled == 0")),
    wrong(VALID, "plain.not_distinct", "A comparison that only some engines have", "rules:they_are_plain", ("o on o.place = e.place", "o on o.place is not distinct from e.place")),
    wrong(VALID, "plain.like", "A comparison in which each engine has letters of its own", "rules:they_are_plain", ("when e.says <> 'order' ", "when e.says not like 'order' ")),
    wrong(VALID, "plain.nulls_last", "An order that only some engines have", "rules:they_are_plain", (OF_NUMBER, OF_NUMBER.replace("order by n", "order by n nulls last"))),
    wrong(MARKS, "plain.now", "The clock of the engine", "rules:they_are_plain", ("where v.why_not is null", "where v.why_not is null and current_timestamp is not null")),
    wrong("tests/test_rules.py", "plain.anything", "The check finds nothing", "rules:the_check_can_fail", ("    return problems\n", "    return []\n")),
    # The engines and the files of DuckDB.
    wrong(ENGINE, "duck.empty_is_nothing", "An empty text is nothing", "raw:what_is_kept_is_what_arrived", (", allow_quoted_nulls = false", "")),
    wrong(ENGINE, "duck.guessed", "DuckDB guesses how a file is meant", "raw:what_is_kept_is_what_arrived", ("auto_detect = false", "auto_detect = true"), (" delim = ',', quote = '\\\"', escape = '\\\"', nullstr = '', allow_quoted_nulls = false, parallel = false", " parallel = false")),
    wrong(ENGINE, "duck.small", "Whole numbers have 32 bits", "raw:what_is_kept_is_what_arrived", ('"whole": "bigint"', '"whole": "integer"')),
    wrong(ENGINE, "duck.short_rows", "A row is as long as DuckDB allows by itself", "raw:a_long_line_stops_nobody", ("{max(longest, 2_097_152)}", "2097152")),
    wrong(ENGINE, "duck.any_path", "A path is put into a statement as it is", "raw:a_folder_with_any_name", ('str(path).replace("\'", "\'\'")', "str(path)")),
    wrong(ENGINE, "duck.fetches", "DuckDB may fetch what it misses", "raw:duckdb_fetches_nothing_while_it_runs", ('"autoinstall_known_extensions": "false"', '"autoinstall_known_extensions": "true"')),
    wrong(STORE, "duck.no_numbers", "The fields have no numbers", "raw:parquet_has_only_what_every_engine_means_the_same_by", (", field_ids {{{numbers}}}", "")),
    wrong(STORE, "duck.place", "The places of lines begin at 0", "raw:parquet_has_only_what_every_engine_means_the_same_by", ("list(enumerate(lines, 1))", "list(enumerate(lines))")),
    wrong(ENGINE, "duck.quotes", "Quotes in a text do not make a row longer", "raw:a_long_line_stops_nobody", (" + value.count('\"') for", " for")),
    wrong(STORE, "duck.packed", "The files are packed in another way", "raw:parquet_has_only_what_every_engine_means_the_same_by", ("(format parquet, ", "(format parquet, compression zstd, ")),
    wrong(STORE, "duck.lines_as_text", "Lines are kept as text", "raw:parquet_has_only_what_every_engine_means_the_same_by", ('[("place", "whole"), ("line", "bytes")], list(enumerate(lines, 1))', '[("place", "whole"), ("line", "text")], list(enumerate(map(str, lines), 1))')),
    wrong(STORE, "duck.breaks", "What is no Parquet breaks the run", "raw:18_a_file_that_cannot_be_read_is_red", ('            except duckdb.Error:\n                raise ValueError("it is no Parquet") from None\n', "            except ZeroDivisionError:\n                raise\n")),
    # The days.
    wrong(DAYS, "days.utc", "A day is a day in UTC", "days:13_what_the_clock_on_the_wall_says days:12_how_many_hours_they_have days:every_moment_is_in_exactly_one_day 12_a_day_with_23_hours", ("zoneinfo.ZoneInfo(zone))", "datetime.UTC)")),
    wrong(DAYS, "days.24_hours", "A day has 24 hours", "days:every_moment_is_in_exactly_one_day days:12_how_many_hours_they_have 12_a_day_with_23_hours 13_a_day_with_25_hours", ("_at(zones, day + ONE, datetime.time()), _at(zones, day + ONE, hour)", "_at(zones, day, datetime.time()) + 86_400_000_000, _at(zones, day + ONE, hour)")),
    wrong(DAYS, "days.second_midnight", "Of two midnights a day begins at the second", "days:12_a_midnight_that_stands_twice_or_never", ("datetime.datetime.combine(day, time, zoneinfo.ZoneInfo(zone)).astimezone", "datetime.datetime.combine(day, time, zoneinfo.ZoneInfo(zone)).replace(fold=1).astimezone")),
    wrong(DAYS, "days.closes_same_day", "A day is closed at 6 in the morning of the same day", "days:13_what_the_clock_on_the_wall_says 09_when_a_day_is_closed", ("_at(zones, day + ONE, hour)", "_at(zones, day, hour)")),
    wrong(DAYS, "days.closes_6_hours_later", "A day is closed 6 hours after it has ended", "days:13_what_the_clock_on_the_wall_says", ("_at(zones, day + ONE, hour)", "_at(zones, day + ONE, datetime.time()) + 21_600_000_000")),
    wrong(DAYS, "days.closes_by_old_clock", "The last day before a move is closed by the old clock", "days:13_the_last_day_before_a_move_is_closed_by_the_new_clock", ("_at(zones, day + ONE, hour)", "_moment(_zone(zones, day), day + ONE, hour)")),
    wrong(DAYS, "days.closes_at_six", "A day is closed at 6, whatever the limits say", "days:09_the_hour_at_which_a_day_is_closed", ("    hour = datetime.time.fromisoformat(closes_at)\n    dates", "    hour = datetime.time(6)\n    dates")),
    wrong(DAYS, "days.closes_at_whole_hours", "The minutes do not matter at which a day is closed", "days:09_the_hour_at_which_a_day_is_closed", ("    hour = datetime.time.fromisoformat(closes_at)\n    dates", "    hour = datetime.time.fromisoformat(closes_at).replace(minute=0)\n    dates")),
    wrong(DAYS, "days.first_zone", "A shop keeps its first clock for ever", "days:13_a_shop_that_moves", ("return begun[-1] if begun", "return begun[0] if begun")),
    wrong(DAYS, "days.as_written", "The clocks are taken in the order in which they were written", "days:13_a_shop_that_moves", ("in sorted(zones) if", "in zones if")),
    wrong(DAYS, "days.zone_a_day_later", "A new clock begins a day later", "days:13_a_shop_that_moves", ("if since <= day.isoformat()", "if since < day.isoformat()")),
    wrong(DAYS, "days.zone_of_the_month", "A new clock begins with its month", "days:13_a_shop_that_moves", ("if since <= day.isoformat()", "if since[:7] <= day.isoformat()[:7]")),
    wrong(DAYS, "days.always_a_zone", "A shop has a clock before it is there", "days:a_shop_that_is_not_there_yet_has_no_days 13_an_order_before_a_shop_is_there", ("return begun[-1] if begun else None", "return begun[-1] if begun else sorted(zones)[0][1]")),
    wrong(DAYS, "days.no_day_before", "Nowhere it is earlier than in UTC", "days:every_moment_has_its_day_wherever_the_shop_is", ("for date in dates for step in (-1, 0, 1)", "for date in dates for step in (0, 1)")),
    wrong(DAYS, "days.no_day_after", "Nowhere it is later than in UTC", "days:every_moment_has_its_day_wherever_the_shop_is", ("for date in dates for step in (-1, 0, 1)", "for date in dates for step in (-1, 0)")),
    wrong(DAYS, "days.always_one", "Without a moment there is a day in 1970", "days:no_moment_no_day", ("    dates = {line.EPOCH.date() + (us // DAY_US) * ONE for us in moments}\n", "    dates = {line.EPOCH.date() + (us // DAY_US) * ONE for us in moments or [0]}\n")),
    wrong(DAYS, "days.machine", "The clock rules are those of the machine", "days:the_list_of_clock_rules_is_the_pinned_one", ("    zoneinfo.reset_tzpath(to=[])\n", "    pass\n")),
    # Settings.
    *(wrong(DAYS, f"settings.{name}", what, "raw:settings_that_cannot_be", change) for name, what, change in (
        ("any_hour", "Any hour is fine", ("    if hour.strftime(\"%H:%M\") != closes_at:\n", "    if False:\n")),
        ("any_name", "Any name of a shop is fine", ("        if not line.NAME.fullmatch(shop):\n", "        if False:\n")),
        ("no_clock", "A shop needs no clock", ("if not zones or len(", "if len(")),
        ("two_clocks", "Of two clocks from one day on the later in the alphabet counts", (" or len({since for since, _ in zones}) < len(zones):", ":")),
        ("any_date", "A date may be written in another way", ("if datetime.date.fromisoformat(since).isoformat() != since or not", "if len(since.split(\"-\")) != 3 or not")),
        ("old_date", "A shop can have been there for ever", (' or not "2000-01-01" <= since <= "2199-12-31":', ' or not since <= "2199-12-31":')),
        ("far_date", "A shop can begin whenever it likes", (' or not "2000-01-01" <= since <= "2199-12-31":', ' or not "2000-01-01" <= since:')),
        ("any_clock", "Whether there is a clock shows when it is needed", ("            if zone not in _clocks():\n", "            if False:\n")),
        ("any_move", "A shop may move to where the day before has not begun", ("                if moments != sorted(set(moments)):\n", "                if False:\n")),
        ("any_midnight", "Two days of a shop that moves may begin at the same moment", ("for time in (datetime.time(), hour):", "for time in (hour,):")),
        ("any_close", "A day of a shop that moves may be closed before the one before it", ("for time in (datetime.time(), hour):", "for time in (datetime.time(),):")),
    )),
    wrong(RUN, "settings.unseen", "Nobody looks at the settings", "raw:settings_that_cannot_be", ("        check(shops, limits)\n", "")),
    wrong(RUN, "settings.any_limit", "A limit may be anything", "raw:settings_that_cannot_be", ("        if type(limits[name]) is not int or not 0 <= limits[name] <= most:\n", "        if False:\n")),
    wrong(RUN, "settings.true_is_1", "True is a number of minutes", "raw:settings_that_cannot_be", ("if type(limits[name]) is not int or", "if not isinstance(limits[name], int) or")),
    wrong(RUN, "settings.last_wins", "Of a name that stands twice in the settings, the last one wins", "raw:settings_in_which_a_name_stands_twice", ("        if len(dict(pairs)) < len(pairs):\n", "        if False:\n")),
    # A line.
    wrong(LINE, "line.any_print", "Nobody compares the fingerprint", "line:01_every_single_bit_counts 01_one_bit_is_flipped", (" or hashlib.sha256(said).hexdigest().encode() != given", "")),
    wrong(LINE, "line.half_a_print", "Only half of the fingerprint is compared", "line:01_every_single_bit_counts", ("hexdigest().encode() != given:", "hexdigest().encode()[:32] != given[:32]:")),
    wrong(LINE, "line.letters", "Large and small letters of the fingerprint are the same", "line:01_every_single_bit_counts", ("hexdigest().encode() != given:", "hexdigest().encode() != given.lower():")),
    wrong(LINE, "line.any_space", "Anything may stand behind the fingerprint", "line:01_every_single_bit_counts", ('if space != b" " or hashlib', "if hashlib")),
    wrong(LINE, "line.trimmed", "Spaces around it are taken off", "line:01_every_cut_and_everything_added_counts", ("record[:64], record[64:65], record[65:]", "record.strip()[:64], record.strip()[64:65], record.strip()[65:]")),
    wrong(LINE, "line.any_order", "The fields may stand in any order", "line:a_right_fingerprint_does_not_make_a_line", ("if not isinstance(pairs, Object) or [name for name, _ in pairs] != FIELDS:", "if isinstance(pairs, Object):\n            pairs = Object(sorted(pairs, key=lambda pair: FIELDS.index(pair[0])))\n        if not isinstance(pairs, Object) or [name for name, _ in pairs] != FIELDS:")),
    wrong(LINE, "line.pairs", "A list of names and values is a line", "line:a_right_fingerprint_does_not_make_a_line", ("if not isinstance(pairs, Object) or ", "if ")),
    wrong(LINE, "line.any_version", "Every version is this one", "line:a_right_fingerprint_does_not_make_a_line", ("type(version) is not int or version != 1 or ", "")),
    wrong(LINE, "line.true_is_1", "True is the number 1", "line:a_right_fingerprint_does_not_make_a_line", ("type(version) is not int or version != 1 or type(n) is not int or", "version != 1 or not isinstance(n, int) or")),
    wrong(LINE, "line.number_0", "The numbers begin at 0", "line:a_right_fingerprint_does_not_make_a_line", ("not 1 <= n < 2**53", "not 0 <= n < 2**53")),
    wrong(LINE, "line.any_number", "A number may be as large as it likes", "line:a_right_fingerprint_does_not_make_a_line", ("not 1 <= n < 2**53", "not 1 <= n")),
    wrong(LINE, "line.largest_number", "The largest number does not fit", "line:what_is_just_allowed", ("not 1 <= n < 2**53", "not 1 <= n < 2**53 - 1")),
    wrong(LINE, "line.small_numbers", "Numbers have 31 bits", "line:what_is_just_allowed", ("not 1 <= n < 2**53", "not 1 <= n < 2**31")),
    wrong(LINE, "line.name_begins", "Only the beginning of a name is looked at", "line:a_right_fingerprint_does_not_make_a_line", ("not NAME.fullmatch(shop) or not NAME.fullmatch(feed)", "not NAME.match(shop) or not NAME.match(feed)")),
    wrong(LINE, "line.longer_names", "A name may be one longer", "line:a_right_fingerprint_does_not_make_a_line", ('"[a-z0-9-]{1,40}"', '"[a-z0-9-]{1,41}"')),
    wrong(LINE, "line.shorter_names", "A name has to be one shorter", "line:what_is_just_allowed", ('"[a-z0-9-]{1,40}"', '"[a-z0-9-]{1,39}"')),
    wrong(LINE, "line.id_begins", "Only the beginning of an id is looked at", "line:a_right_fingerprint_does_not_make_a_line", ("not ID.fullmatch(event_id)", "not ID.match(event_id)")),
    wrong(LINE, "line.longer_ids", "An id may be one longer", "line:a_right_fingerprint_does_not_make_a_line", ('_:-]{1,100}"', '_:-]{1,101}"')),
    wrong(LINE, "line.shorter_ids", "An id has to be one shorter", "line:what_is_just_allowed", ('_:-]{1,100}"', '_:-]{1,99}"')),
    wrong(LINE, "line.time_begins", "Only the beginning of a time is looked at", "line:a_right_fingerprint_does_not_make_a_line", ("MOMENT.fullmatch(received_at)", "re.match(MOMENT.pattern[:-1], received_at)")),
    wrong(LINE, "line.any_year", "Any year is fine", "line:a_right_fingerprint_does_not_make_a_line", ("        if not FIRST_US <= micros(moment) < LAST_US:\n            raise ValueError\n", "")),
    wrong(LINE, "line.first_moment", "The first moment does not fit", "line:what_is_just_allowed", ("if not FIRST_US <= micros(moment) < LAST_US:", "if not FIRST_US < micros(moment) < LAST_US:")),
    wrong(LINE, "line.last_moment", "The last moment does not fit", "line:what_is_just_allowed", ("if not FIRST_US <= micros(moment) < LAST_US:", "if not FIRST_US <= micros(moment) < LAST_US - 1:")),
    wrong(LINE, "line.one_moment_more", "The first moment of 2200 fits", "line:a_right_fingerprint_does_not_make_a_line", ("if not FIRST_US <= micros(moment) < LAST_US:", "if not FIRST_US <= micros(moment) <= LAST_US:")),
    wrong(LINE, "line.spare_bits", "A body can be written in several ways", "line:a_right_fingerprint_does_not_make_a_line", ("if base64.b64encode(bytes_of_it).decode() != body or len(bytes_of_it) > LARGEST:", "if len(bytes_of_it) > LARGEST:")),
    wrong(LINE, "line.any_size", "A body may be as large as it likes", "line:a_right_fingerprint_does_not_make_a_line", (" or len(bytes_of_it) > LARGEST:", ":")),
    wrong(LINE, "line.a_byte_less", "The largest body does not fit", "line:what_is_just_allowed line:any_bytes_can_be_a_body", ("len(bytes_of_it) > LARGEST", "len(bytes_of_it) >= LARGEST")),
    wrong(LINE, "line.not_empty", "An empty body does not fit", "line:what_is_just_allowed", ("or len(bytes_of_it) > LARGEST", "or not 0 < len(bytes_of_it) <= LARGEST")),
    wrong(LINE, "line.body_is_text", "A body is a text", "line:any_bytes_can_be_a_body", ("micros(moment), bytes_of_it)", 'micros(moment), bytes_of_it.decode("utf-8", "replace").encode())')),
    wrong(LINE, "line.broken_bytes", "What is not UTF-8 is left out", "line:a_right_fingerprint_does_not_make_a_line", ('said.decode("utf-8")', 'said.decode("utf-8", "ignore")')),
    wrong(LINE, "line.seconds", "The times are in whole seconds", "line:a_line_is_read 11_too_old_and_from_the_future", ("event_id, micros(moment), bytes_of_it)", "event_id, micros(moment) // 1_000_000 * 1_000_000, bytes_of_it)")),
    # What has to add up.
    wrong(RUN, "run.missing_is_fine", "Nobody asks what is missing", "02_a_line_is_dropped 04_a_spoiled_copy_comes_instead storm:what_is_lost_is_red_until_it_is_sent_again", ("if missing := last - len(there):", "if (missing := last - len(there)) > 9:")),
    wrong(RUN, "run.only_behind", "The last numbers are not missing", "02_a_line_is_dropped", ("if missing := last - len(there):", "if missing := max(there, default=0) - len(there):")),
    wrong(RUN, "run.more_is_fine", "Nobody asks what is too much", "22_more_arrives_than_was_announced", ("        if above := sum(", "        if above := 0 * sum(")),
    wrong(RUN, "run.unannounced_is_fine", "A shop that is not announced is fine", "22_more_arrives_than_was_announced", ('last = closing["numbers"].get(shop, 0)', 'last = closing["numbers"].get(shop, 0) or max(numbers[shop], default=0)')),
    wrong(RUN, "run.later_is_too_much", "What was received after the closing is too much", "22_what_was_received_after_the_closing_is_for_the_next_one storm:closings_in_between", (' and received_us < closing["at_us"] for', " for")),
    wrong(RUN, "run.at_the_moment", "What was received at the moment of the closing was received before", "22_what_was_received_after_the_closing_is_for_the_next_one", ('received_us < closing["at_us"] for', 'received_us <= closing["at_us"] for')),
    wrong(RUN, "run.all_of_it", "Nothing at all may be missing, whatever was announced", "22_what_was_received_after_the_closing_is_for_the_next_one", ("        there = sorted(n for n in numbers.get(shop, ()) if n <= last)\n", "        last = max([last, *numbers.get(shop, ())])\n        there = sorted(n for n in numbers.get(shop, ()) if n <= last)\n")),
    wrong(RUN, "run.who_arrived", "A shop of which nothing arrived is not missed", "02_nothing_arrived_of_a_shop raw:nothing_has_arrived_yet", ('    for shop, last in sorted(closing["numbers"].items()):\n        there', '    for shop, last in sorted((shop, last) for shop, last in closing["numbers"].items() if shop in numbers):\n        there')),
    wrong(RUN, "run.first_of_the_last", "The first missing number is the one after the last", "02_a_line_is_dropped", ("next((rank for rank, n in enumerate(there, 1) if n != rank), len(there) + 1)", "len(there) + 1")),
    wrong(RUN, "run.contradiction", "A contradiction is not said", "23_two_lines_with_one_number 23_a_contradiction_behind_a_missing_number", ("in lines.items() if len(prints) > 1]", "in lines.items() if len(prints) > 9]")),
    wrong(RUN, "run.contradiction_later", "A contradiction is only said when a day is closed", "23_two_lines_with_one_number", ("in lines.items() if len(prints) > 1]", "in lines.items() if len(prints) > 1 and closing]")),
    wrong(RUN, "run.no_clock", "A shop needs no clock", "13_a_shop_without_a_clock raw:13_a_shop_gets_its_clock_later", ('    found += [f"{shop} has no clock" for shop in {shop for shop, _ in lines} | announced if shop not in shops]\n', "")),
    wrong(RUN, "run.no_clock_yet", "A shop needs no clock as long as nothing has come of it", "13_a_shop_without_a_clock", ("{shop for shop, _ in lines} | announced if", "{shop for shop, _ in lines} if")),
    wrong(RUN, "run.nothing_announced", "A shop needs a clock even if nothing is announced of it", "13_a_shop_without_a_clock", ('closing["numbers"].items() if n}', 'closing["numbers"].items()}')),
    wrong(RUN, "run.too_early", "What comes after a closing and was received before it is fine", "raw:26_a_closing_that_was_asked_too_early_is_red", ('        found += _above(numbers, closing_before, "the closing before")\n', "        pass\n")),
    wrong(RUN, "run.too_early_later", "That a closing was asked too early shows only at the next one", "raw:26_a_closing_that_was_asked_too_early_is_red", ('    if closing_before is not None:\n        found += _above', '    if closing is not None and closing_before is not None:\n        found += _above')),
    wrong(RUN, "run.feed_of_two", "A feed may belong to two shops", "24_a_feed_belongs_to_one_shop", ("if len(of_it) > 1]", "if len(of_it) > 9]")),
    wrong(RUN, "run.one_each", "Nobody asks whether each line has one verdict", "00_verdicts_that_cannot_be_right", ('        found.append("a line has no verdict, or more than one")\n', "        pass\n")),
    wrong(RUN, "run.one_each_later", "Only when a day is closed each line has to have one verdict", "00_verdicts_that_cannot_be_right", ("    if [one.place for one in came] != [row.place for row in rows]:", "    if closing and [one.place for one in came] != [row.place for row in rows]:")),
    wrong(RUN, "run.any_verdict", "Nobody asks whether a verdict can be", "00_verdicts_that_cannot_be_right", ("if not _can_be(one, row)]:", "if False]:")),
    wrong(RUN, "run.any_sum", "Nobody asks whether the verdicts add up", "00_verdicts_that_cannot_be_right", ('if name != "reasons" and counted["raw"] != sum(', 'if name == "nobody" and counted["raw"] != sum(')),
    wrong(RUN, "run.sum_of_all", "Only all of it together has to add up", "00_verdicts_that_cannot_be_right", ('if name != "reasons" and counted', 'if name == "all" and counted')),
    *(wrong(RUN, f"run.{name}", what, "00_verdicts_that_cannot_be_right", change) for name, what, change in (
        ("another_line", "A verdict may be about another line", ("(row.shop, row.n, row.received_us) == (one.shop, one.n, one.received_us) and row.verdict", "row.verdict")),
        ("fifth_kind", "There may be a fifth kind of verdict", (" and row.verdict in KINDS and bool(row.reason)", " and bool(row.reason)")),
        ("without_reason", "A verdict needs no reason", (" and bool(row.reason) and marks", " and marks")),
        ("any_marks", "Anything may be late", (" and bool(row.reason) and marks\n", " and bool(row.reason)\n")),
        ("marks_of_the_bad", "What is bad may have marks", ("in (0, 1) and (valid or not getattr(row, mark)) for", "in (0, 1) for")),
        ("spoiled_or_not", "What is spoiled may have any reason", ('bool(one.spoiled) == (row.reason == "spoiled") and ', "")),
        ("valid_or_not", "A day and a reason belong to nobody", ('valid == (row.reason == "an order") == (row.shop_day is not None) and ', "")),
        ("any_cents", "The cents of a verdict are nobody's business", (" and row.cents == (one.cents if valid else 0)", "")),
    )),
    wrong(RUN, "run.no_mark", "A mark that is nothing breaks the run", "00_verdicts_that_cannot_be_right", ("getattr(row, mark) or 0 for", "getattr(row, mark) for")),
    wrong(RUN, "run.no_verdict", "A verdict that is nothing breaks the run", "00_verdicts_that_cannot_be_right", ("str(row.verdict): 1", "row.verdict: 1")),
    wrong(RUN, "run.no_cents", "A verdict without cents breaks the run", "00_verdicts_that_cannot_be_right", ("row.cents or 0", "row.cents")),
    wrong(RUN, "run.every_moment", "Every moment that an order names gets a day", "11_any_moment_that_can_be_written", ("if one.placed_us is not None and one.received_us - oldest_us <= one.placed_us <= one.received_us + future_us}", "if one.placed_us is not None}")),
    wrong(RUN, "run.days_of_the_new", "Only an order that is hours old at most gets a day", "11_an_order_of_weeks_ago_comes_alone", ("one.received_us - oldest_us <= one.placed_us <=", "one.received_us - 86_400_000_000 <= one.placed_us <=")),
    wrong(RUN, "run.days_without_35", "An order that is exactly 35 days old gets no day", "11_alone_at_the_limits", ("one.received_us - oldest_us <= one.placed_us <=", "one.received_us - oldest_us < one.placed_us <=")),
    wrong(RUN, "run.days_without_5", "An order that is minutes ahead gets no day", "11_alone_at_the_limits", ("<= one.placed_us <= one.received_us + future_us}", "<= one.placed_us <= one.received_us}")),
    wrong(RUN, "run.body_in_print", "Two bodies have one fingerprint", "05_another_body_under_the_same_id", ("_print(found.body), found.received_us", "_print(found.body[:30]), found.received_us")),
    wrong(RUN, "run.reasons", "Nobody counts the reasons", "raw:a_list_says_what_a_run_did", ('found["reasons"][f"{row.verdict}: {row.reason}"] += 1', 'found["reasons"][row.verdict] += 1')),
    # The counter outside, by which all of it is measured.
    *(blind(at, what) for at, what in enumerate(("the_shop", "the_number", "the_verdict", "the_reason", "the_day", "the_cents", "what_is_late", "what_is_out_of_order", "what_is_more", "the_moment"))),
    wrong(COUNT, "count.problems", "The counter does not look at the problems", "00_the_counter_sees_every_difference", ("    if sorted(problems) != sorted(wanted_problems):\n", "    if False:\n")),
    wrong(COUNT, "count.places", "The counter does not look whether each line has one verdict", "00_the_counter_sees_every_difference", ("    if [row[0] for row in rows] != list(range(1, len(deliveries) + 1)):\n", "    deliveries = deliveries[: len(rows)]\n    if False:\n")),
    # What was said once.
    wrong(RUN, "said.anything", "What was said once may change", "raw:25_other_settings_do_not_change_what_was_said raw:25_another_rule_does_not_change_what_was_said", ('if old.verdict != "waiting" and old != new]:', "if False]:")),
    wrong(RUN, "said.only_the_verdict", "Of what was said once only the verdict stays", "raw:25_other_settings_do_not_change_what_was_said raw:25_another_rule_does_not_change_what_was_said", ('if old.verdict != "waiting" and old != new]:', 'if old.verdict != "waiting" and old.verdict != new.verdict]:')),
    wrong(RUN, "said.waits_for_ever", "What waits once waits for ever", "raw:07_what_waits_may_change_and_nothing_else storm:any_number_of_batches_and_runs", ('if old.verdict != "waiting" and old != new]:', "if old != new]:")),
    wrong(RUN, "said.fewer_numbers", "A closing may take numbers back", "raw:26_a_closing_that_takes_something_back_is_red", ("if now < last or now > last and", "if now > last and")),
    wrong(RUN, "said.same_moment", "Two closings of one moment may differ", "raw:26_a_closing_that_takes_something_back_is_red", ('if now < last or now > last and closing["at_us"] == closing_before["at_us"]:', "if now < last:")),
    wrong(RUN, "said.earlier", "A closing may be asked for an earlier moment", "raw:26_a_closing_that_takes_something_back_is_red", ('        if closing["at_us"] < closing_before["at_us"]:\n', "        if False:\n")),
    wrong(RUN, "said.only_the_last", "After a run without a closing the one before is forgotten", "raw:26_a_closing_that_takes_something_back_is_red", ('next((one["closing"] for one in reversed(green) if one["closing"] is not None), None)', 'green[-1]["closing"]')),
    wrong(RUN, "said.red_once", "Whoever was red once may say what they like", "raw:25_other_settings_do_not_change_what_was_said raw:26_a_closing_that_takes_something_back_is_red", ('green = [one for _, one in past if not one["problems"]]', "green = [one for _, one in past]")),
    # The files.
    wrong(RUN, "files.only_new", "Only the new lines are judged", "raw:a_run_adds_up raw:07_what_waits_may_change_and_nothing_else", ("            lines += fresh\n", "            lines = fresh if fresh else lines\n")),
    wrong(RUN, "files.nothing_new", "Without new lines nothing is judged", "raw:a_run_without_anything_new", ("= self._made(past, raw, came, self.shops, self.limits, closing)", "= self._made(past, raw, came if not past or len(raw) > len(past[-1][1][\"raw\"]) else [], self.shops, self.limits, closing)")),
    wrong(RUN, "files.when", "A list says when it was written", "raw:the_same_again_says_the_same", ('"clock": clock(),', '"clock": clock(), "when": __import__("time").time_ns(),')),
    wrong(RUN, "files.any_content", "Nobody compares a listed file", "raw:18_any_change_of_a_listed_file_is_red", ("-{_print(data)[:16]}\\{self.store.ending}", "-[0-9a-f]{{16}}\\{self.store.ending}"), ("            if known.get(name, one) != one:\n", "            if False:\n")),
    wrong(RUN, "files.any_place", "Nobody compares a listed file, or the last list with it", "raw:18_two_files_that_changed_places_are_red", ("-{_print(data)[:16]}\\{self.store.ending}", "-[0-9a-f]{{16}}\\{self.store.ending}"), ("            if known.get(name, one) != one:\n", "            if False:\n"), ("        if not fits:\n", "        if False:\n")),
    wrong(RUN, "files.unlisted", "Until a file is listed anything may happen to it", "raw:18_what_happens_to_a_file_before_it_is_listed_is_red", ("-{_print(data)[:16]}\\{self.store.ending}", "-[0-9a-f]{{16}}\\{self.store.ending}")),
    wrong(RUN, "files.any_names", "Nobody asks for the names of the raw files", "raw:18_a_file_that_nobody_took_is_red", ('            if not re.fullmatch(rf"[0-9]{{6,}}-{_print(data)[:16]}\\{self.store.ending}", name):\n                raise Red(f"raw/{name!a} is not what was taken")\n', "")),
    wrong(RUN, "files.name_begins", "Only the beginning of a name is looked at", "raw:18_a_file_that_nobody_took_is_red", ("if not re.fullmatch(rf", "if not re.match(rf")),
    wrong(RUN, "files.gone", "A listed file may be gone, and nobody compares the last list", "raw:18_two_files_that_changed_their_names_are_red raw:18_any_change_of_a_listed_file_is_red", ('                raise Red(f"raw/{name!a} is gone")\n', "                continue\n"), ("        if not fits:\n", "        if False:\n")),
    wrong(RUN, "files.unreadable", "What cannot be read breaks the run", "raw:18_a_file_that_cannot_be_read_is_red", ('            except ValueError:\n                raise Red(f"raw/{name!a} cannot be read") from None\n', "            except ZeroDivisionError:\n                raise\n")),
    wrong(RUN, "files.folder", "A folder between the files breaks the run", "raw:18_a_file_that_nobody_took_is_red", ('            except OSError:\n                raise Red(f"raw/{name!a} cannot be read") from None\n', "            except ZeroDivisionError:\n                raise\n")),
    wrong(RUN, "files.other_form", "Verdicts of another form break the run", "raw:18_verdicts_of_another_form_are_red", ("        except (ValueError, TypeError):\n            raise Red(f\"the verdicts of run", "        except ZeroDivisionError:\n            raise Red(f\"the verdicts of run")),
    wrong(RUN, "settings.any_closing", "A closing may be anything", "raw:a_closing_that_is_none", ("            check_closing(closing)\n", "            pass\n")),
    wrong(RUN, "settings.no_end", "A limit may be as large as it likes", "raw:settings_that_cannot_be", ("not 0 <= limits[name] <= most", "not 0 <= limits[name]")),
    wrong(RUN, "settings.one_more", "A limit may be one larger", "raw:settings_that_cannot_be", ("not 0 <= limits[name] <= most", "not 0 <= limits[name] <= most + 1")),
    wrong(RUN, "settings.one_less", "The largest limit is too large", "raw:the_largest_limits", ("not 0 <= limits[name] <= most", "not 0 <= limits[name] < most")),
    wrong(RUN, "settings.any_number", "The numbers of a closing may be anything", "raw:a_closing_that_is_none", ("type(n) is not int or not 0 <= n < 2**53 or not line", "not line")),
    wrong(RUN, "settings.true_is_4", "True is a number of a closing", "raw:a_closing_that_is_none", ("if any(type(n) is not int or", "if any(not isinstance(n, int) or")),
    wrong(RUN, "settings.any_moment", "A closing may be asked for any moment", "raw:a_closing_that_is_none", ("    if type(at_us) is not int or not line.FIRST_US <= at_us < min(line.LAST_US, now_us() + 300_000_000):\n", "    if type(at_us) is not int:\n")),
    wrong(RUN, "settings.ahead", "A closing may be asked for a moment that has not come", "raw:26_a_closing_whose_moment_has_not_come", ("min(line.LAST_US, now_us() + 300_000_000)", "line.LAST_US")),
    wrong(RUN, "settings.same_clock", "Two machines have the same clock", "raw:26_a_closing_whose_moment_has_not_come", ("now_us() + 300_000_000)", "now_us() + 1)")),
    wrong(RUN, "settings.other_clock", "The clock of the machine stands still", "raw:26_a_closing_whose_moment_has_not_come", ("    return time.time_ns() // 1000\n", "    return line.LAST_US\n")),
    wrong(RUN, "settings.any_at", "The moment of a closing may be anything", "raw:a_closing_that_is_none", ("    if type(at_us) is not int or not line", "    if not line")),
    wrong(RUN, "settings.any_shop", "The shops of a closing may be anything", "raw:a_closing_that_is_none", (" or not line.NAME.fullmatch(shop) for shop", " for shop")),
    wrong(RUN, "files.verdicts_unseen", "Nobody compares the verdicts", "raw:18_verdicts_that_add_up_and_are_wrong_are_red", ('if not self._was_kept("verdicts", number, one["verdicts"]):', "if False:")),
    wrong(RUN, "files.other_verdicts", "The file of the verdicts has the days of other lines", "raw:the_verdicts_in_the_file_are_those_of_the_run", ("[list(row) for row in rows])}, rows", "[list(row._replace(shop_day=rows[at - 1].shop_day)) for at, row in enumerate(rows)])}, rows")),
    wrong(RUN, "files.verdicts_anywhere", "The verdicts may lie anywhere", "raw:18_verdicts_under_another_name_are_red", ('return re.fullmatch(name, one["file"]) and ', "return ")),
    wrong(RUN, "files.verdicts_name_begins", "Only the beginning of the name of the verdicts is looked at", "raw:18_verdicts_under_another_name_are_red", ('return re.fullmatch(name, one["file"]) and ', 'return re.match(name, one["file"]) and ')),
    wrong(RUN, "files.unreadable_is_empty", "A folder that cannot be read is an empty one", "raw:18_a_folder_that_cannot_be_read_is_red", ('            raise Red(f"{kind} cannot be read") from None\n', "            return []\n")),
    wrong(RUN, "files.no_folder_yet", "A folder that is not there yet cannot be read", "raw:nothing_has_arrived_yet", ("            if isinstance(problem, FileNotFoundError) and not folder.is_symlink():\n                return []\n", "")),
    wrong(RUN, "files.link_to_nothing", "A link that leads nowhere is an empty folder", "raw:18_a_folder_that_cannot_be_read_is_red", (" and not folder.is_symlink():\n", ":\n")),
    wrong(RUN, "files.list_is_folder", "A folder in the place of a list breaks the run", "raw:18_a_list_that_is_nothing_is_red", ("            try:\n                data = path.read_bytes()\n                one = json.loads(data)\n", "            data = path.read_bytes()\n            try:\n                one = json.loads(data)\n")),
    wrong(RUN, "files.says_names", "The name of a raw file is said as it is", "raw:18_a_file_that_nobody_took_is_red", ('raise Red(f"raw/{name!a} is not what was taken")', 'raise Red(f"raw/{name} is not what was taken")')),
    wrong(RUN, "files.says_lists", "The name of a list is said as it is", "raw:18_a_file_that_nobody_took_is_red", ('raise Red(f"runs/{path.name!a} cannot be read', 'raise Red(f"runs/{path.name} cannot be read')),
    wrong(STORE, "store.never_ends", "What is no folder is a file that somebody has written already", "raw:18_a_folder_that_cannot_be_read_is_red", ("            raise NotADirectoryError(f\"{folder.name!a} is no folder\") from None\n", "            raise\n")),
    wrong(RUN, "files.any_closing", "The closing in the last list may be anything", "raw:26_a_closing_in_the_last_list_that_nobody_could_ask_is_red", ('                check_closing(last["closing"])\n', "                pass\n")),
    wrong(RUN, "files.list_name", "A list may have any name", "raw:18_a_list_under_another_name_is_red", ('path.name == f"{number:06}.json" and ', "")),
    wrong(RUN, "files.no_chain", "A list does not name the one before it", "raw:18_every_word_of_an_older_list_counts", (' and one["before"] == (past[-1][0] if past else "")', "")),
    wrong(RUN, "files.may_shrink", "A list may know fewer files than the one before it", "raw:18_lists_that_lose_a_file_are_red", ("if not follows or not grows or not", "if not follows or not")),
    wrong(RUN, "files.says_anything", "Nobody asks whether the last list fits its verdicts", "raw:18_a_list_that_says_more_than_its_verdicts_is_red", ("        if not fits:\n", "        if False:\n")),
    wrong(RUN, "files.only_counts", "Of the last list only the counts have to fit", "raw:18_a_list_that_says_more_than_its_verdicts_is_red", ("fits = _print(_written(one)) == print_of_it", 'fits = one["counts"] == last["counts"]')),
    wrong(RUN, "files.same_meaning", "The last list may be written in another way", "raw:18_the_last_list_written_in_another_way_is_red", ("fits = _print(_written(one)) == print_of_it", "fits = one == last")),
    wrong(RUN, "files.seen_is_not_enough", "The last list has to come out once more, even if somebody has seen it", "raw:18_the_last_list_written_in_another_way_is_red raw:18_a_list_of_another_version_needs_its_witness", ("        if not past or witness == past[-1][0]:\n", "        if not past:\n")),
    wrong(RUN, "files.any_version", "A list of another version needs nobody who has seen it", "raw:18_a_list_of_another_version_needs_its_witness", ('            raise Red("the last list was written by another version of the program or with other clock rules, and no witness has seen it")\n', "            return\n")),
    wrong(RUN, "files.accuses", "Whatever goes wrong, the last list is said to be wrong", "raw:18_why_the_last_list_cannot_be_worked_out_is_said raw:18_a_list_of_settings_that_cannot_be_is_red", ('f"the last list cannot be worked out once more: {type(problem).__name__}"', '"the last list is not what comes out of the same lines once more"')),
    wrong(RUN, "files.all_its_words", "What went wrong is said with all its words", "raw:18_why_the_last_list_cannot_be_worked_out_is_said", ("{type(problem).__name__}\") from None", "{type(problem).__name__}\") from problem")),
    wrong(RUN, "files.any_settings", "The last list may come out of settings that cannot be", "raw:18_a_list_of_settings_that_cannot_be_is_red", ('            check(last["shops"], last["limits"])\n', "")),
    wrong(RUN, "files.any_rules", "With other clock rules nobody needs to have seen the last list", "raw:18_a_list_of_another_version_needs_its_witness", ('(last.get("program"), last.get("clock")) != (program(), clock())', 'last.get("program") != program()')),
    wrong(RUN, "files.any_engine", "Another version of an engine is the same program", "raw:a_list_says_what_a_run_did", (' | {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "duckdb": _version("duckdb")}', "")),
    wrong(RUN, "files.twice", "A list may name a file twice, or anything else", "raw:18_a_list_that_says_more_than_its_verdicts_is_red", (' or not _are_files(one["raw"]):', ":")),
    wrong(RUN, "files.too_deep", "A list that is too deep breaks the run", "raw:18_a_list_that_is_nothing_is_red", ("AttributeError, OSError, RecursionError):", "AttributeError, OSError):")),
    wrong(RUN, "files.no_witness", "Nobody asks the witness", "raw:18_the_witness_sees_what_nobody_else_can", ("        if witness is not None and witness not in", "        if witness == 0 and witness not in")),
    wrong(RUN, "files.empty_witness", "An empty witness is none", "raw:18_the_witness_sees_what_nobody_else_can", ("        if witness is not None and witness not in", "        if witness and witness not in")),
    wrong(RUN, "files.strict_witness", "If a run dies before anybody has its witness, all others are red", "raw:21_a_run_that_dies_before_anybody_has_its_witness", ("for print_of_it, _ in past)][-2:]:", "for print_of_it, _ in past)][-1:]:")),
    wrong(RUN, "files.old_witness", "Any old witness is fine", "raw:21_a_run_that_dies_before_anybody_has_its_witness", ("for print_of_it, _ in past)][-2:]:", "for print_of_it, _ in past)]:")),
    wrong(RUN, "files.no_program", "A list does not say what decided", "raw:a_list_says_what_a_run_did", ('_print(path.read_bytes()) for path in sorted(files)}', '"" for path in sorted(files)}')),
    wrong(RUN, "files.no_clock", "A list does not say which clock rules", "raw:a_list_says_what_a_run_did", ('"clock": clock(),', '"clock": "some",')),
    wrong(RUN, "files.one_engine", "Another engine judges than the one that was chosen", "raw:the_engine_that_was_chosen_judges", ("rows = judge(came, shops, limits, self.engine_of)", "rows = judge(came, shops, limits)")),
    wrong(RUN, "files.unfinished", "Files that were never finished are read", "raw:21_what_a_run_left_that_died_is_in_nobodys_way", ('if not path.name.startswith(".")', "if True")),
    wrong(RUN, "files.gives_up", "Whoever takes the same lines at the same moment loses them", "raw:21_two_who_take_at_the_same_moment_are_both_kept", ("                number += 1\n", "                return None\n")),
    wrong(RUN, "files.one_name", "The verdicts of a run that died are in the way of the next one", "raw:21_a_run_that_dies_after_its_verdicts_is_simply_done_again raw:21_two_runs_at_the_same_moment", ("            except FileExistsError:\n                if (self.folder / kind / name).read_bytes() != data:\n                    more += 1\n                    continue\n", "            except ZeroDivisionError:\n                raise\n")),
    wrong(RUN, "files.by_its_name", "What a run left that died is believed by its name", "raw:21_a_run_that_dies_after_its_verdicts_is_simply_done_again", ("                if (self.folder / kind / name).read_bytes() != data:\n", "                if False:\n")),
    wrong(RUN, "files.faster", "Whoever is second breaks", "raw:21_two_runs_at_the_same_moment", ("        except FileExistsError:\n            raise Red(f\"another run was faster", "        except ZeroDivisionError:\n            raise Red(f\"another run was faster")),
    wrong(STORE, "store.over", "A file is written over", "raw:a_file_is_written_once raw:21_two_who_take_at_the_same_moment_are_both_kept", ("        os.link(part, path)\n", "        os.replace(part, path)\n")),
    wrong(STORE, "store.in_place", "A file is written where it will be", "raw:21_whoever_dies_while_writing_leaves_no_file raw:21_killed_at_any_moment", ('    part = path.with_name(f".{path.name}.{secrets.token_hex(8)}")\n', "    part = path\n"), ("        os.link(part, path)\n        on_disk(path.parent)\n    finally:\n        part.unlink(missing_ok=True)\n", "        on_disk(path.parent)\n    finally:\n        pass\n")),
    wrong(STORE, "store.leaves_parts", "What was not finished is left behind", "raw:21_whoever_dies_while_writing_leaves_no_file", ("        part.unlink(missing_ok=True)\n", "        pass\n")),
    wrong(STORE, "store.one_part", "What was not finished is in the way of the next one", "raw:21_what_a_run_left_that_died_is_in_nobodys_way raw:21_killed_at_any_moment", ('f".{path.name}.{secrets.token_hex(8)}"', 'f".{path.name}"')),
    wrong(STORE, "store.no_flush", "Nothing has been written when it is said to be", "raw:21_whoever_dies_while_writing_leaves_no_file", ("            file.flush()\n", "")),
    wrong(STORE, "store.lines_end", "A line ends where it has a line break", "raw:what_is_kept_is_what_arrived", ('base64.b64encode(line) + b"\\n" for line in lines', 'line + b"\\n" for line in lines'), ("base64.b64decode(line, validate=True) for line", "line for line")),
    wrong(STORE, "store.any_base64", "What is no base64 is passed over", "raw:18_a_file_that_cannot_be_read_is_red", ("base64.b64decode(line, validate=True)", "base64.b64decode(line)")),
    # What must not be merged yet.
    wrong(TESTS, "hold.followed", "A link is followed, and what it leads to is said", "hold:a_link_makes_it_wait_and_is_not_followed", ("if [ -f HOLD ] && [ ! -L HOLD ]; then", "if [ -f HOLD ]; then")),
    wrong(TESTS, "hold.nowhere", "A link to nothing is fine", "hold:a_link_makes_it_wait_and_is_not_followed", ("elif [ -e HOLD ] || [ -L HOLD ]; then", "elif [ -e HOLD ]; then")),
    wrong(TESTS, "hold.folder", "A folder is fine", "hold:a_folder_makes_it_wait", ("elif [ -e HOLD ] || [ -L HOLD ]; then", "elif [ -L HOLD ]; then")),
    wrong(TESTS, "hold.green", "It says so and is green", "hold:a_branch_that_has_to_wait_is_red_in_the_end", ('HOLD)"\n  exit 1', 'HOLD)"\n  exit 0')),
    wrong(TESTS, "hold.other_name", "Another file makes it wait", "hold:a_branch_that_has_to_wait_is_red_in_the_end", ("if [ -f HOLD ] && [ ! -L HOLD ]; then", "if [ -f WAIT ] && [ ! -L WAIT ]; then")),
    wrong(TESTS, "hold.any_name", "Any file that begins like it makes it wait", "hold:only_that_file_makes_it_wait", ("if [ -f HOLD ] && [ ! -L HOLD ]; then", "if ls HOLD* > /dev/null 2>&1 && [ ! -d HOLD ] && [ ! -L HOLD ]; then")),
    wrong(STORE, "store.not_on_disk", "Nobody asks whether a file is on the disk", "raw:21_what_was_kept_survives_a_power_failure", ("            os.fsync(file.fileno())\n", "")),
    wrong(STORE, "store.no_name_on_disk", "Nobody asks whether the name of a file is on the disk", "raw:21_what_was_kept_survives_a_power_failure", ("        os.link(part, path)\n        on_disk(path.parent)\n", "        os.link(part, path)\n")),
    wrong(STORE, "store.no_folder_on_disk", "Nobody asks whether the name of a new folder is on the disk", "raw:21_what_was_kept_survives_a_power_failure", ("        on_disk(folder.parent)\n", "")),
    wrong(STORE, "store.other_folder", "The folder itself is asked for, and not the one in which its name stands", "raw:21_what_was_kept_survives_a_power_failure", ("        on_disk(folder.parent)\n", "        on_disk(folder)\n")),
    wrong(STORE, "store.only_the_last", "Only the last of several new folders is asked for", "raw:21_what_was_kept_survives_a_power_failure", ("        made(folder.parent)\n", "        folder.parent.mkdir(parents=True, exist_ok=True)\n")),
    wrong(STORE, "store.any_end", "The last line needs no end", "raw:18_a_file_that_cannot_be_read_is_red", ("    if rest:\n", "    if False:\n")),
]


def here(of, *begins):
    """Without DuckDB the mistakes in what is only for DuckDB are left out. Where every engine has to be there, they are in."""
    there = importlib.util.find_spec("duckdb") or os.environ.get("EVERY_ENGINE")
    return [one for one in of if there or not one.name.startswith(begins)]


ALL = here(EVERY_ONE, "duck.")


def noticed(text_of, file, tests):
    """What the tests say of a copy with another text in one file."""
    with tempfile.TemporaryDirectory() as folder:
        for part in PARTS:
            shutil.copytree(ROOT / part, pathlib.Path(folder, part), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "shops.json", folder)
        if file:
            pathlib.Path(folder, file).write_text(text_of, encoding="utf-8")
        done = subprocess.run([sys.executable, "-B", "-c", RUNNER, *tests], cwd=folder, capture_output=True, text=True, timeout=600)
    if done.returncode:
        return {"run": 0, "failed": [], "broke": [["all", done.stderr.strip().splitlines()[-1][:200]]]}
    return json.loads(done.stdout)


def answer(one):
    """Empty if every test that has to notice it does."""
    said = noticed(one.put_into((ROOT / one.file).read_text(encoding="utf-8")), one.file, one.noticed_by)
    useless = [text for _, text in said["failed"] + said["broke"] if NOT_EVEN_RUN.search(text)]
    if useless or not said["run"]:
        return f"it does not even run: {(useless or [text for _, text in said['broke']])[0].splitlines()[-1]}"
    seen = {name for name, _ in said["failed"] + said["broke"]}
    left = [test for test in one.noticed_by if test not in seen]
    return f"not noticed by {', '.join(left)}" if left else ""


def chosen(words, of):
    if len(words) == 1 and "/" in words[0]:
        part, parts = map(int, words[0].split("/"))
        if not 1 <= part <= parts:
            raise SystemExit("There is no such part.")
        return of[part - 1 :: parts]
    unknown = set(words) - {one.name for one in of}
    if unknown:
        raise SystemExit(f"There is no {', '.join(sorted(unknown))}.")
    return [one for one in of if not words or one.name in words]


def main(words, of=ALL):
    if len({one.name for one in of}) != len(of):
        raise SystemExit("Two mistakes have the same name.")
    these = chosen(words, of)
    tests = sorted({test for one in these for test in one.noticed_by})
    clean = noticed("", "", tests)
    if clean["failed"] or clean["broke"] or clean["run"] < len(tests):
        raise SystemExit(f"The unchanged copy does not pass: {clean}")
    lines, missed = ["| Mistake | Noticed |", "|---|---|"], 0
    with concurrent.futures.ThreadPoolExecutor(int(os.environ.get("AT_ONCE", os.cpu_count() or 1))) as pool:
        for one, said in zip(these, pool.map(answer, these), strict=True):
            missed += bool(said)
            lines.append(f"| {one.what} (`{one.name}`) | {said or 'yes'} |")
            if said:
                print(f"{one.name}: {said}")
    lines.append(f"| **{len(these)} mistakes** | **{len(these) - missed}** |")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    print(f"{len(these)} mistakes, {missed} not noticed")
    return missed > 0 or not these


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
