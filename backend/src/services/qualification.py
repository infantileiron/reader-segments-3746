"""分群资格取样与触达可达名单。两者都绑定一个完整权益版本。"""
from datetime import date

from fastapi import HTTPException

from src.models.entities import EntitlementVersion, Reader
from src.services.entitlement import (
    entitled_on, explain_day_gap, explain_week_gap, latest_version, snapshot_for_version,
    week_bounds, week_status,
)


def resolve_version(s, requested):
    """返回一个完整权益版本记录；不可混用不同版本。"""
    if requested is not None:
        version = s.query(EntitlementVersion).filter_by(version=requested).first()
        if not version:
            raise HTTPException(409, f'权益版本 v{requested} 不存在')
        return version
    version = latest_version(s)
    if not version:
        raise HTTPException(409, '尚无生效的权益版本，请先核验订阅批次')
    return version


def qualify(s, week_start, version):
    """按所选自然周取样：整周 7 天都有权益的会员纳入，其余记录排除依据。"""
    week_start, week_end = week_bounds(week_start)
    ranges = snapshot_for_version(s, version.version)
    readers = s.query(Reader).order_by(Reader.id).all()

    included, excluded = [], []
    for reader in readers:
        member_ranges = ranges.get(reader.code, [])
        full, days, segments = week_status(member_ranges, week_start, week_end)
        if full:
            included.append({
                'code': reader.code,
                'reader_id': reader.id,
                'covered_days': days,
                'week_ranges': segments,
                'ranges': _ranges_json(member_ranges),
            })
        else:
            reason, detail = explain_week_gap(member_ranges, week_start, week_end)
            excluded.append({
                'code': reader.code,
                'reader_id': reader.id,
                'reason': reason,
                'covered_days': days,
                **detail,
            })

    not_in_roster = sorted(set(ranges) - {reader.code for reader in readers})
    basis = {
        'entitlement_version': version.version,
        'version_checksum': version.checksum,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'rule': '所选自然周周一至周日 7 天均有有效订阅权益才纳入取样；重叠订阅合并计天，退款按对应订单截断。',
        'included': [
            {'code': row['code'], 'covered_days': row['covered_days'], 'week_ranges': row['week_ranges'],
             'ranges': row['ranges']}
            for row in included
        ],
        'excluded': excluded,
        'not_in_roster': not_in_roster,
        'counts': {'included': len(included), 'excluded': len(excluded),
                   'not_in_roster': len(not_in_roster), 'readers': len(readers)},
    }
    return included, excluded, basis


def _ranges_json(member_ranges):
    return [
        {'start': row['start'].isoformat(), 'end': row['end'].isoformat(), 'days': row['days'],
         'orders': row['orders']}
        for row in member_ranges
    ]


def build_reachability(s, segment, cluster_id, send_date, version):
    ranges = snapshot_for_version(s, version.version)
    members = [m for m in segment.result.get('members', []) if m['cluster_id'] == cluster_id]
    reachable, excluded = [], []
    for member in members:
        member_ranges = ranges.get(member['code'], [])
        if entitled_on(member_ranges, send_date):
            reachable.append(member['code'])
        else:
            reason, detail = explain_day_gap(member_ranges, send_date)
            excluded.append({
                'code': member['code'],
                'reason': reason,
                **detail,
            })
    basis = {
        'entitlement_version': version.version,
        'version_checksum': version.checksum,
        'send_date': send_date.isoformat(),
        'segment_id': segment.id,
        'cluster_id': cluster_id,
        'rule': '触达按发送日重算：当天在任一有效订阅区间内即可达；退款按对应订单截断，其他订单仍计。',
        'included': [{'code': code, 'ranges': _ranges_json(ranges.get(code, []))} for code in reachable],
        'excluded': excluded,
        'counts': {'included': len(reachable), 'excluded': len(excluded), 'members': len(members)},
    }
    return reachable, excluded, basis


def default_send_date():
    return date.today()
