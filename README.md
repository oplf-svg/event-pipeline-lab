# event-pipeline-lab

Part of the public portfolio of Luis Orozco. The other repositories stand at [github.com/oplf-svg](https://github.com/oplf-svg).

Is to turn the orders of [webhook-platform](https://github.com/oplf-svg/webhook-platform) into totals, and to show for every total
which orders are in it. The company behind it is made up: no shop, customer or order in here is real.

## The claim, not proven yet

> Every total goes back to raw events.

Records are flipped, dropped, doubled, delayed and spoiled. What is spoiled or doubled has to be set aside and counted, what is dropped has
to be missed, and what is delayed may change nothing. That is here. The totals are not.

## What is here so far

| | |
|---|---|
| [The strict reader](pipeline/reader.py) | Says whether the body of an event is an order, and why not. It has to say the same as webhook-platform, which is written in another language |
| [144 bodies](examples/bodies.jsonl) | What both have to say of each, byte for byte. The answers of 38 stand in [a test of webhook-platform](https://github.com/oplf-svg/webhook-platform/blob/main/tests/Platform.Tests/OrderTests.cs). The other 106 were asked there once, by hand, and one answer of this reader was put right by that |
| [What it has to survive](docs/contract.md) | 26 things that can happen, and what must be true afterwards. Two of them come with the totals |
| [The rules](rules) | Four files of SQL give each line one verdict. In the tests SQLite and DuckDB run the same text, and have to say the same |
| [One at a time](tests/test_rows.py) and [everything at once](tests/test_storm.py) | Lines arrive in any order, doubled, spoiled or not at all, over several runs. Every storm is different |
| [Counted from outside](outside/count.py) | A program that knows what really happened, and uses nothing of the pipeline |
| Tests that can fail | [73 mistakes](tests/wrong.py) in the reader and [301](tests/wrong_rules.py) in the rules, the days, the lines and the files, one at a time. Each names what has to notice it |

Why so strict: Python's own reader takes `NaN`, a name that stands twice, UTF-16 and a BOM, and for Python `true` is the whole
number 1. A pipeline that takes more than the platform would count what the platform cannot read.

## Run the tests

They need Python 3.12. Two packages are put into `build/venv`, each checked against its fingerprint.

```bash
bash .github/scripts/tests.sh
bash .github/scripts/wrong.sh
```

## Who made this

Directed and approved by Luis Orozco. Code, tests and texts are written by Claude, an AI agent that proposes its changes under an
identity of its own. The owner corrects the [rules](rules) and the SQL of the totals. The second is not here yet.

Licensed under the [Apache License 2.0](LICENSE), see also [NOTICE](NOTICE).
