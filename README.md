# event-pipeline-lab

Part of the public portfolio of Luis Orozco. The other repositories stand at [github.com/oplf-svg](https://github.com/oplf-svg).

Turns the orders of [webhook-platform](https://github.com/oplf-svg/webhook-platform) into totals, and shows for every total
which orders are in it. The company behind it is made up: no shop, customer or order in here is real.

## The claim, not proven yet

> Every total goes back to raw events.

Records will be flipped, dropped, doubled, delayed and spoiled. Each of them has to be found, set aside and counted. Nothing of
that is here yet.

## What is here so far

| | |
|---|---|
| [The strict reader](pipeline/reader.py) | Says whether the body of an event is an order, and why not. It has to say the same as webhook-platform, which is written in another language |
| [99 bodies](examples/bodies.jsonl) | What both have to say of each, byte for byte. The answers of 38 stand in [a test of webhook-platform](https://github.com/oplf-svg/webhook-platform/blob/main/tests/Platform.Tests/OrderTests.cs). The other 61 follow from reading its code and were not run there yet |
| [Tests that can fail](tests/wrong.py) | 61 mistakes that are easy to make, one at a time. The bodies have to notice each of them |

Why so strict: Python's own reader takes `NaN`, a name that stands twice, UTF-16 and a BOM, and for Python `true` is the whole
number 1. A pipeline that takes more than the platform would count orders that the platform never made.

## Run the tests

They need Python 3.12 or newer and nothing else.

```bash
bash .github/scripts/tests.sh
bash .github/scripts/wrong.sh
```

## Who made this

Directed and approved by Luis Orozco. Code, tests and texts are written by Claude, an AI agent that proposes its changes under an
identity of its own. The owner corrects the rules and the SQL of the totals. Neither is here yet.

Licensed under the [Apache License 2.0](LICENSE), see also [NOTICE](NOTICE).
