"""Split-the-bill maths as pure functions. Shares always add up EXACTLY to the bill (integer paise)."""


def split_equal(total_paise: int, n: int) -> list[int]:
    """n amounts that sum exactly to total; the extra paise go to the first shares."""
    total_paise, n = int(total_paise), int(n)
    if n < 1:
        raise ValueError("n must be at least 1")
    if total_paise < 0:
        raise ValueError("total can't be negative")
    base, extra = divmod(total_paise, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def split_by_items(lines: list[dict], payers: list, shared_line_ids=()) -> dict:
    """lines: [{id, payer, amount_paise}] for accepted items. payers: who pays (e.g. guest ids), in order.
    A line goes to its payer; lines marked shared, or whose payer isn't in `payers`, are split equally.
    Returns {payer: amount_paise}; the values sum exactly to the sum of the lines."""
    if not payers:
        raise ValueError("need at least one payer")
    shared_ids = set(shared_line_ids or ())
    out = {p: 0 for p in payers}
    shared_total = 0
    for line in lines:
        amt = int(line["amount_paise"])
        if line["id"] in shared_ids or line.get("payer") not in out:
            shared_total += amt
        else:
            out[line["payer"]] += amt
    for p, part in zip(payers, split_equal(shared_total, len(payers))):
        out[p] += part
    return out
