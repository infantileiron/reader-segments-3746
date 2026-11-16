"""权益区间口径：修订接纳、退款截断、重叠合并。"""
from datetime import date

from src.services.entitlement import merge_ranges, truncate_end, week_bounds, week_start_of


def d(text):
    return date.fromisoformat(text)


def test_week_bounds_normalizes_to_monday():
    assert week_start_of(d('2026-11-11')) == d('2026-11-09')
    start, end = week_bounds(d('2026-11-12'))
    assert (start, end) == (d('2026-11-09'), d('2026-11-15'))
    assert (end - start).days + 1 == 7


def test_merge_overlapping_orders_counts_days_once():
    merged = merge_ranges([
        (d('2026-11-01'), d('2026-11-10'), 'A'),
        (d('2026-11-08'), d('2026-11-20'), 'B'),
    ])
    assert len(merged) == 1
    assert merged[0]['start'] == d('2026-11-01')
    assert merged[0]['end'] == d('2026-11-20')
    assert merged[0]['days'] == 20
    assert merged[0]['orders'] == ['A', 'B']


def test_merge_adjacent_days_are_contiguous():
    merged = merge_ranges([
        (d('2026-11-01'), d('2026-11-07'), 'A'),
        (d('2026-11-08'), d('2026-11-14'), 'B'),
    ])
    assert len(merged) == 1
    assert merged[0]['days'] == 14


def test_merge_keeps_gaps_separate():
    merged = merge_ranges([
        (d('2026-11-01'), d('2026-11-03'), 'A'),
        (d('2026-11-06'), d('2026-11-08'), 'B'),
    ])
    assert [row['days'] for row in merged] == [3, 3]


def test_refund_truncates_only_its_order():
    end = truncate_end(d('2026-11-30'), d('2026-11-15'))
    assert end == d('2026-11-14')
    assert truncate_end(d('2026-11-30'), None) == d('2026-11-30')
    # 退款日恰好是开始日 -> 该订单不再贡献任何天数
    assert truncate_end(d('2026-11-30'), d('2026-11-09')) == d('2026-11-08')
