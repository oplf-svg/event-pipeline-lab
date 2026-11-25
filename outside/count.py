"""Counts from outside: what the pipeline says of each line, against what really happened. It uses nothing of the pipeline."""

import collections


def differences(story, deliveries, rows, problems=(), wanted_problems=()):
    """Every difference, in words. Nothing means that each line got exactly the verdict that it has to have.

    rows: (place, shop, n, verdict, reason, shop_day, cents, late, out_of_order, more, received_us), place by place.
    """
    found = []
    if [row[0] for row in rows] != list(range(1, len(deliveries) + 1)):
        return [f"{len(deliveries)} lines arrived and {len(rows)} places have a verdict: {collections.Counter(row[0] for row in rows).most_common(2)}"]
    here = collections.defaultdict(set)
    for delivery in deliveries:
        if delivery.intact:
            sent = story.sent[delivery.place_in_story]
            here[sent.shop].add(sent.n)
    complete = {shop: next(n for n in range(1, max(numbers) + 2) if n not in numbers) for shop, numbers in here.items()}
    late_comers, seen = story.out_of_order(), set()
    for delivery, row in zip(deliveries, rows, strict=True):
        sent = story.sent[delivery.place_in_story]
        if not delivery.intact:
            wanted = (None, None, "bad", "spoiled", None, 0, 0, 0, 0, None)
        elif delivery.place_in_story in seen:
            wanted = (sent.shop, sent.n, "duplicate", "the same line", None, 0, 0, 0, 0, sent.received_us)
        elif sent.n > complete[sent.shop]:
            wanted = (sent.shop, sent.n, "waiting", "behind a missing number", None, 0, 0, 0, 0, sent.received_us)
        else:
            wanted = (sent.shop, sent.n, sent.verdict, sent.reason, sent.day, sent.cents, sent.late, int(delivery.place_in_story in late_comers), sent.more, sent.received_us)
        if delivery.intact:
            seen.add(delivery.place_in_story)
        if tuple(row[1:]) != wanted:
            found.append(f"place {row[0]}: {tuple(row[1:])} instead of {wanted}")
    if sorted(problems) != sorted(wanted_problems):
        found.append(f"it says {sorted(problems)} instead of {sorted(wanted_problems)}")
    return found


def sums(story, deliveries):
    """What it has to add up to, for each shop and in all, if every number has arrived."""
    copies = collections.Counter(delivery.place_in_story for delivery in deliveries if delivery.intact)
    late_comers, found = story.out_of_order(), collections.defaultdict(collections.Counter)
    for place, sent in enumerate(story.sent):
        for name in ("all", f"shop {sent.shop}"):
            found[name]["raw"] += copies[place]
            found[name][sent.verdict] += 1
            # Whatever a line is, the copies that came after it are duplicates.
            found[name]["duplicate"] += copies[place] - 1
            for key, value in (("cents", sent.cents), ("late", sent.late), ("out_of_order", int(place in late_comers)), ("more", sent.more)):
                found[name][key] += value
    broken = sum(not delivery.intact for delivery in deliveries)
    found["all"]["raw"] += broken
    found["all"]["bad"] += broken
    keys = ("raw", "valid", "duplicate", "bad", "waiting", "cents", "late", "out_of_order", "more")
    return {name: {key: counter[key] for key in sorted(keys)} for name, counter in found.items()}
