# What this has to survive

The claim is: **every total goes back to raw events.** It counts as proven only when tests that could have failed did not. The
totals come later. This page is about what stands before them: every line that arrived gets one verdict with a reason, and a line
that did not arrive is missed. The tests, the rules and the code can each be checked against it.

## A line

The exporter of webhook-platform is to write one line for each event that it has stored, and for each other body that came under a
used id. It is sent at least once, and the same bytes each time.

`<64 hex> {"v":1,"shop":"north","n":1042,"feed":"north-web","event_id":"evt_7","received_at":"2027-03-28T22:59:59.123456Z","body":"<base64>"}`

- The 64 hex are the SHA-256 of everything behind the space. A fingerprint of the body alone would not see a changed shop.
- `n` counts for each shop from 1, without gaps. It alone decides which of two lines was first, whatever the order in which they
  arrive, so any broker will do.
- An id belongs to its feed. On another feed it is another one.
- `received_at` is when the event was received for the first time, by the clock of the database.
- A **closing** is asked from the database and does not come with the lines: a moment, and for each shop the last `n` of everything
  that was received before it, the **announced** number. It may only be asked when all of that has its number.

## One verdict for each line

The first rule that fits decides. What comes to rule 4 is judged in the order of its numbers. The rules are four files of SQL,
[lines](../rules/lines.sql), [valid](../rules/valid.sql), [marks](../rules/marks.sql) and [verdicts](../rules/verdicts.sql), and their [limits](../rules/limits.json). A run uses one engine. In the tests SQLite and DuckDB
run the same text, and have to say the same. Other engines come later, so the rules only use words and signs from a short list, and ids and
order numbers are compared as fingerprints: some engines take large and small letters for the same.

| | What it is | Verdict |
|---|---|---|
| 1 | Its fingerprint does not fit, or it cannot be read | bad: spoiled. It takes no number, so that is missing, unless the line came as well |
| 2 | Another line has the same number, and both fingerprints fit | bad: contradicts, and **the run is red.** Nobody can say which one is right, so each copy of them is bad |
| 3 | The same line was there already, whatever stands before it | duplicate |
| | A number before it is missing, or contradicts itself | waiting, until that is put right |
| 4 | Its feed and id stood at a lower number | duplicate, if its body is the one that stood there first. Otherwise bad: another body |
| 5 | The body is no order, as webhook-platform reads it | bad, with the reason |
| 6 | It was placed more than 5 minutes after it was received, or more than 35 days before | bad: from the future, too old |
| 7 | The shop has no clock for that day | bad: no day for this shop. If it has none at all, **the run is red** |
| 8 | Its feed and order number stood at a lower number, in an order that was the first line of its id | bad: number used |
| 9 | Anything else | valid |

**What has to be true.** The run works it out from the lines, and not from what the rules made of them. Otherwise it is red. Whether a rule
is right it cannot say: that an order is too old, or a number used, only the tests look at.

- At a closing nothing is missing up to the announced number of each shop
- Each line has one verdict, about this line, with a reason. Only a valid one has a day, cents and marks
- `raw = valid + duplicate + bad + waiting`, for each shop and in all. A spoiled line belongs to no shop
- No number has two different lines, no feed belongs to two shops, and every shop has a clock
- A number above the announced one that was received at that moment or later may be here already, and is for the next closing. One that was
  received before is red
- What was said once stays, unless it waits. No closing announces less than the one before, and nothing comes afterwards that was received
  before it and was not announced. Only a run that was not red has a say

**Marks** are counted and are in no sum, because what has them is valid: *late* was received at or after 6 in the morning of the day
after its own, *out of order* has a higher number than a valid order that was placed later, *more* has fields that nobody knows.

**A day** is a day on the clock of its shop. It ends when the next one begins, so it can have 23 or 25 hours, and from the first day of a
shop on no moment is in none or in two. The days are rows of a table, so for them the rules only compare whole numbers.

## Files

Raw lines, verdicts, and one list for each run. Lines and verdicts are Parquet or plain text. Each file is written once, all of it or
nothing. The name of a raw file holds the beginning of its fingerprint, so it shows if its content is another one before it is listed.
That it is gone before that, or was exchanged together with its name, shows at most by the numbers that are missing then. A list names every file with its
fingerprint, what it adds up to, the settings, the fingerprints of the rules and the program, and the list before it. The next run looks
at all raw files and all that a list names first, and lists nothing if something does not fit.

Nothing in the folder vouches for the last list: its fingerprint is the **witness** of a run, and somebody else has to keep it. They may
be one run behind, because a run can die before anybody has its witness. If nobody has seen the last list, it has to be what comes out
once more of the same lines, settings and closing. Only the same program can say that: after a new version of it, of Python, SQLite, DuckDB
or the package with the clock rules, somebody has to have seen that list. Older lists are not worked out once more. Who vouches for them is the list after
them, and for the last one the witness.

## What can happen, and what must be true afterwards

Each row is about a line with which nothing else is wrong.

| | What happens | What must be true |
|---|---|---|
| 1 | Any bit of a line is flipped, or it is cut | Spoiled |
| 2 | A line is dropped: the first, one in the middle, the last, or all of a shop | At a closing it is missing: how many, and the first of them. What stands behind it waits. Sent again, all is as if nothing had happened |
| 3 | A line that is not spoiled is doubled, at once or much later | Duplicate |
| 4 | A spoiled copy comes before the good one, or instead of it | Before: nothing is lost. Instead: the number is missing |
| 5 | Another body under a used id, whichever arrives or was received first | The body at the lowest number counts. Another one is bad at each number at which it stands |
| 6 | A body that cannot be read comes twice under one id | Bad once, duplicate once |
| 7 | Any order of arrival, any batches, any number of runs | The same verdicts. What was once said of a number stays, unless it waits or another line with that number or a lower one comes |
| 8 | A valid order with a lower number was placed later | Marked as out of order |
| 9 | An order that is not too old is received when its day is closed already | Valid and late. At 05:59:59.999999 it is not late, at 06:00:00 it is |
| 10 | Nothing arrives here for two days, and then all at once | Late is decided by when webhook-platform received it |
| 11 | An order from the future or of long ago, or with any moment that can be written | Exactly 5 minutes and exactly 35 days still count. One microsecond more does not |
| 12 | A day with 23 hours | 22:59:59Z on 28 March 2027 is that day in London, 23:00:00Z is the next |
| 13 | A day with 25 hours, shops on other clocks, a shop that moves, or that has no clock yet | Every valid order is in exactly one day of its own shop. Before the first day of its shop it is bad. Without any clock the run is red |
| 14 | Fractions of a cent | *Comes with the totals* |
| 15 | A field that nobody knows, from the middle of a day on | Valid and marked |
| 16 | A field that is read gets another name, from the middle of a day on | Bad with the reason. Nothing is guessed |
| 17 | Anything that a body can be | The answer of webhook-platform |
| 18 | A file or a list that is named by a list that is there is changed, cut, taken away or exchanged, or a raw file is put there whose name does not fit. The last list is neither the one that somebody has seen nor the one after it, or nobody has seen it and it says something else than what comes out | Red, and nothing is listed |
| 19 | No order at all on a day | *Comes with the totals* |
| 20 | The same order number on two channels of a shop | Two orders. Twice on one channel, each time in an order that is the first line of its id: the second is bad |
| 21 | A run dies at any moment, or two run at once | Nothing half written is ever read, and the next run does it. If two in a row die between their list and its witness, or if one does and the program is another one then, a person has to look first |
| 22 | Something arrives that was received at the moment of the closing or later, with a number above the announced one | It is for the next closing, and may have gaps. At one microsecond before the moment it has to be announced |
| 23 | Two or three different lines with one number, also behind a missing one | Red. They and their copies are bad, and what stands behind them waits instead of being judged without them |
| 24 | A feed comes under two shops | Red |
| 25 | A limit, a clock or a rule is changed so that something that was said would be another thing | Red, until it is as it was |
| 26 | A closing announces less than one before it that was not red, was asked too early, or its moment is five minutes ahead or more | Red, or refused |

## What it does not do yet

- There are no totals, no late versions of a day and no Kafka.
- What is red because of a line that came stays red: two lines with one number, a feed that came under two shops, and at every closing a line
  with a number that is far too high. So does what comes after a closing that was green and had been asked too early. A person has no way
  yet to say what does not count.
- Every run reads and judges all lines again, and its list names all files again. That keeps it simple, and is not for millions of lines.
- A limit holds for ever. Nobody can say yet from which day on there is another one. A clock can: a shop moves from a date on.
- Whoever can write all files can tell another story, if nobody keeps the witness or if they can change that too. The same holds for whoever
  can make a line with its fingerprint: the secrets of the feeds stay with webhook-platform, so trust begins at its exporter.
