"""权益版本：订阅订单修订 -> 完整权益快照。

口径
- 每个订单接纳修订号最大的记录，与到达顺序无关；迟到的旧修订不回退。
- 退款把对应订单的区间截断到退款日前一天；其他订单继续有效。
- 重叠/相接的订阅先合并区间，再按去重后的自然日计天。
"""
import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import date, timedelta

from sqlalchemy import text

from src.models.entities import (
    EntitlementSnapshot, EntitlementVersion, SubscriptionBatch, SubscriptionEvent,
)

WEEK_DAYS = 7
_ENTITLEMENT_LOCK = threading.RLock()


@contextmanager
def entitlement_lock(s):
    """序列化版本落库；PostgreSQL 额外用事务级 advisory lock 跨进程互斥。"""
    with _ENTITLEMENT_LOCK:
        if s.bind.dialect.name == 'postgresql':
            s.execute(text('SELECT pg_advisory_xact_lock(3107)'))
        yield


@contextmanager
def key_lock(s, key):
    """按任意字符串键串行化同一幂等键的导入；PostgreSQL 用两参数 advisory lock。"""
    with _ENTITLEMENT_LOCK:
        if s.bind.dialect.name == 'postgresql':
            # 用 hashtext 把键映射为 32 位整数，再与固定命名空间组合成 advisory lock。
            s.execute(text('SELECT pg_advisory_xact_lock(3108, hashtext(:k))'), {'k': key})
        yield


def week_start_of(day):
    """把任意日期归一到所在自然周的周一。"""
    return day - timedelta(days=day.weekday())


def week_bounds(week_start):
    start = week_start_of(week_start)
    return start, start + timedelta(days=WEEK_DAYS - 1)


def default_week(today=None):
    """最近一个已结束的完整自然周（周一为起点）。"""
    today = today or date.today()
    return week_start_of(today) - timedelta(days=WEEK_DAYS)


def merge_ranges(intervals):
    """intervals: [(start, end, order_no)]，合并重叠与相接区间。"""
    spans = []
    for start, end, order_no in intervals:
        if end < start:
            continue
        spans.append((start, end, order_no))
    spans.sort(key=lambda x: (x[0], x[1]))
    merged = []
    for start, end, order_no in spans:
        if merged and start <= merged[-1]['end'] + timedelta(days=1):
            if end > merged[-1]['end']:
                merged[-1]['end'] = end
            merged[-1]['orders'].append(order_no)
        else:
            merged.append({'start': start, 'end': end, 'orders': [order_no]})
    for row in merged:
        row['days'] = (row['end'] - row['start']).days + 1
        row['orders'] = list(dict.fromkeys(row['orders']))
    return merged


def truncate_end(effective_end, refunded_on):
    if refunded_on is None:
        return effective_end
    return min(effective_end, refunded_on - timedelta(days=1))


def accepted_events(events):
    """每个订单取修订号最大的记录。"""
    latest = {}
    for event in events:
        current = latest.get(event.order_no)
        if current is None or event.revision > current.revision:
            latest[event.order_no] = event
    return list(latest.values())


def member_ranges(events):
    """按会员合并：先按订单截断退款，再合并重叠区间。"""
    by_member = {}
    for event in accepted_events(events):
        by_member.setdefault(event.member_code, []).append(
            (event.effective_start, truncate_end(event.effective_end, event.refunded_on), event.order_no)
        )
    return {code: merge_ranges(spans) for code, spans in by_member.items()}


def build_snapshot(events):
    ranges_by_member = member_ranges(events)
    rows = []
    for code in sorted(ranges_by_member):
        for row in ranges_by_member[code]:
            rows.append({
                'member_code': code,
                'start_date': row['start'],
                'end_date': row['end'],
                'days': row['days'],
                'source_orders': row['orders'],
            })
    payload = [[row['member_code'], row['start_date'].isoformat(), row['end_date'].isoformat()] for row in rows]
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return rows, checksum


def latest_version(s):
    return s.query(EntitlementVersion).order_by(EntitlementVersion.version.desc()).first()


def effective_events(s):
    return (
        s.query(SubscriptionEvent)
        .join(SubscriptionBatch, SubscriptionEvent.batch_id == SubscriptionBatch.id)
        .filter(SubscriptionBatch.state == 'effective')
        .order_by(SubscriptionEvent.order_no, SubscriptionEvent.revision)
        .all()
    )


def create_version(s, batch_id, created):
    """从所有已生效批次重算完整快照；内容未变则复用上一版本。"""
    rows, checksum = build_snapshot(effective_events(s))
    current = latest_version(s)
    if current and current.checksum == checksum:
        return current
    meta = EntitlementVersion(
        version=(current.version if current else 0) + 1,
        batch_id=batch_id,
        created=created,
        checksum=checksum,
        members=len({row['member_code'] for row in rows}),
        ranges=len(rows),
    )
    s.add(meta)
    s.flush()
    for row in rows:
        s.add(EntitlementSnapshot(
            version=meta.version,
            member_code=row['member_code'],
            start_date=row['start_date'],
            end_date=row['end_date'],
            days=row['days'],
            source_orders=row['source_orders'],
        ))
    s.flush()
    return meta


def snapshot_for_version(s, version):
    rows = (
        s.query(EntitlementSnapshot)
        .filter(EntitlementSnapshot.version == version)
        .order_by(EntitlementSnapshot.member_code, EntitlementSnapshot.start_date)
        .all()
    )
    ranges = {}
    for row in rows:
        ranges.setdefault(row.member_code, []).append({
            'start': row.start_date, 'end': row.end_date, 'days': row.days,
            'orders': row.source_orders or [],
        })
    return ranges


def covers(ranges, start, end):
    """ranges 已合并；判断单段区间是否整段覆盖 [start, end]。"""
    return any(r['start'] <= start and r['end'] >= end for r in ranges)


def entitled_on(ranges, day):
    return any(r['start'] <= day <= r['end'] for r in ranges)


def covered_days(ranges, start, end):
    total = 0
    for r in ranges:
        lo = max(r['start'], start)
        hi = min(r['end'], end)
        if lo <= hi:
            total += (hi - lo).days + 1
    return total


def week_status(ranges, week_start, week_end):
    """返回 (是否整周有权益, 已覆盖天数, 周内覆盖片段, 周边景)。"""
    segments = []
    for r in ranges:
        lo = max(r['start'], week_start)
        hi = min(r['end'], week_end)
        if lo <= hi:
            segments.append({'start': lo.isoformat(), 'end': hi.isoformat()})
    days = covered_days(ranges, week_start, week_end)
    return covers(ranges, week_start, week_end), days, segments


def explain_week_gap(ranges, week_start, week_end):
    """给周取样被排除的会员一个可读依据。"""
    if not ranges:
        return '没有订阅订单或订单已全部退款', {'ranges': []}
    _, days, segments = week_status(ranges, week_start, week_end)
    detail = {'covered_days': days, 'week_ranges': segments, 'ranges': [_range_json(r) for r in ranges]}
    if days == 0:
        return '所选自然周内没有有效订阅覆盖', detail
    return f'所选自然周仅覆盖{days}/7天，不足整周', detail


def explain_day_gap(ranges, day):
    """给发送日不可达的会员一个可读依据。"""
    if not ranges:
        return '没有订阅订单或订单已全部退款', {'ranges': []}
    detail = {'ranges': [_range_json(r) for r in ranges]}
    before = [r for r in ranges if r['end'] < day]
    after = [r for r in ranges if r['start'] > day]
    if before:
        detail['last_covered_end'] = max(r['end'] for r in before).isoformat()
    if after:
        detail['next_covered_start'] = min(r['start'] for r in after).isoformat()
    return '发送日不在任何有效订阅区间内', detail


def _range_json(row):
    return {'start': row['start'].isoformat(), 'end': row['end'].isoformat(), 'days': row['days']}
