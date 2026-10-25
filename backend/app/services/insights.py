"""Spending calculations in Asia/Kolkata, mirroring mobile/src/domain/insights.ts."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
DAY_MS = 86_400_000


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _ist(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).astimezone(IST)


def start_of_day(ms: int) -> int:
    d = _ist(ms)
    return _ms(datetime(d.year, d.month, d.day, tzinfo=IST))


def start_of_week(ms: int) -> int:
    return start_of_day(ms) - _ist(ms).weekday() * DAY_MS  # Monday = 0


def start_of_month(ms: int) -> int:
    d = _ist(ms)
    return _ms(datetime(d.year, d.month, 1, tzinfo=IST))


def start_of_next_month(ms: int) -> int:
    d = _ist(ms)
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return _ms(datetime(year, month, 1, tzinfo=IST))


def start_of_previous_month(ms: int) -> int:
    d = _ist(ms)
    year, month = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return _ms(datetime(year, month, 1, tzinfo=IST))


@dataclass(frozen=True)
class Tx:
    amount_minor_units: int
    transaction_datetime: int
    status: str
    transaction_type: str
    category_id: str | None
    deleted_at: int | None


def counts_as_spending(t: Tx, excluded_categories: set[str]) -> bool:
    return (
        t.deleted_at is None
        and t.status == "confirmed"
        and t.transaction_type == "expense"
        and (t.category_id is None or t.category_id not in excluded_categories)
    )


def total_in_range(txs: Iterable[Tx], excluded: set[str], start: int, end: int) -> int:
    return sum(
        t.amount_minor_units for t in txs if start <= t.transaction_datetime < end and counts_as_spending(t, excluded)
    )


def percent_of(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return (part * 100 + whole // 2) // whole


def round_half_up(numerator: int, denominator: int) -> int:
    """Exact integer equivalent of JavaScript's Math.round(n / d) for d > 0 (Python's round() is banker's)."""
    return (2 * numerator + denominator) // (2 * denominator)


@dataclass
class Summary:
    today: int
    week: int
    month: int
    daily_average: int
    days_elapsed: int
    previous_month_same_period: int
    change_percent: int | None
    period_label: str


def build_summary(txs: list[Tx], excluded: set[str], now_ms: int) -> Summary:
    day = start_of_day(now_ms)
    tomorrow = day + DAY_MS
    month_start = start_of_month(now_ms)
    prev_start = start_of_previous_month(now_ms)
    day_of_month = _ist(now_ms).day
    prev_days = (month_start - prev_start) // DAY_MS
    comparable = min(day_of_month, prev_days)

    month = total_in_range(txs, excluded, month_start, tomorrow)
    prev_same = total_in_range(txs, excluded, prev_start, prev_start + comparable * DAY_MS)
    change = round_half_up((month - prev_same) * 100, prev_same) if prev_same > 0 else None
    return Summary(
        today=total_in_range(txs, excluded, day, tomorrow),
        week=total_in_range(txs, excluded, start_of_week(now_ms), tomorrow),
        month=month,
        daily_average=round_half_up(month, day_of_month),
        days_elapsed=day_of_month,
        previous_month_same_period=prev_same,
        change_percent=change,
        period_label=f"Day 1–{day_of_month} of this month vs day 1–{comparable} of last month",
    )


def category_breakdown(
    txs: list[Tx], excluded: set[str], start: int, end: int
) -> list[tuple[str | None, int, int, int]]:
    """Returns (category_id, total, count, percent), largest first."""
    buckets: dict[str | None, list[int]] = {}
    grand = 0
    for t in txs:
        if start <= t.transaction_datetime < end and counts_as_spending(t, excluded):
            b = buckets.setdefault(t.category_id, [0, 0])
            b[0] += t.amount_minor_units
            b[1] += 1
            grand += t.amount_minor_units
    rows = [(cid, total, count, percent_of(total, grand)) for cid, (total, count) in buckets.items()]
    return sorted(rows, key=lambda r: (-r[1], r[0] or ""))
