from datetime import timedelta
from decimal import Decimal


def format_inr(amount: Decimal) -> str:
    """Indian digit grouping: 1234567.5 -> ₹12,34,567.50"""
    whole, fraction = f"{amount:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    text = ",".join([*groups, tail])
    return f"₹{text}" if fraction == "00" else f"₹{text}.{fraction}"


def format_duration(delta: timedelta) -> str:
    """timedelta(minutes=2, seconds=30) -> '2 min 30 s'"""
    seconds = max(int(delta.total_seconds()), 0)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds or not parts:
        parts.append(f"{seconds} s")
    return " ".join(parts)
