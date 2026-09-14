"""Money formatting for buyer-facing text. Amounts are integer paise."""


def _group_en_in(rupees: int) -> str:
    """Indian digit grouping: 1234567 -> "12,34,567"."""
    digits = str(rupees)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])


def format_inr(paise: int) -> str:
    """``145000`` -> ``"₹1,450.00"``; ``12345678`` -> ``"₹1,23,456.78"``."""
    sign = "-" if paise < 0 else ""
    rupees, remainder = divmod(abs(int(paise)), 100)
    return f"{sign}₹{_group_en_in(rupees)}.{remainder:02d}"
