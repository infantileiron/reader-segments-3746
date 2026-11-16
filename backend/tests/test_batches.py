"""批次导入、核验、乱序修订与重试幂等。"""
from src.config.database import Session
from tests.conftest import add_reader, order

WEEK = '2026-11-09'


def make_batch(client, headers, rows, name='订单批次', key=None):
    payload = {'name': name, 'rows': rows}
    if key:
        payload['import_key'] = key
    r = client.post('/batches', json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def verify(client, headers, batch_id):
    return client.post(f'/batches/{batch_id}/verify', headers=headers)


def member_ranges(client, headers, code, version=1):
    r = client.get(f'/entitlements/{version}/members/{code}', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()['ranges']


def test_bad_rows_are_isolated_and_reported(client, users):
    add_reader(client, users['analyst'], 'SL-1')
    batch = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1'),
        {'order_no': '', 'member_code': 'SL-1', 'revision': 1,
         'effective_start': '2026-11-09', 'effective_end': '2026-11-30'},
        {'order_no': 'O-2', 'member_code': 'SL-1', 'revision': 1,
         'effective_start': '2026-12-01', 'effective_end': '2026-11-01'},
        order('O-3', 'SL-1'),
    ])
    assert batch['state'] == 'pending'
    assert batch['accepted_rows'] == 2
    assert batch['rejected_rows'] == 2
    assert len(batch['rejected']) == 2
    assert {row['line'] for row in batch['rejected']} == {2, 3}

    verified = verify(client, users['admin'], batch['id'])
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body['state'] == 'effective'
    assert body['entitlement_version'] == 1
    assert body['problem_rows'] == 2


def test_non_object_rows_are_isolated(client, users):
    batch = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1'),
        'not-an-object',
        42,
        None,
    ])
    assert batch['accepted_rows'] == 1
    assert batch['rejected_rows'] == 3
    assert [row['line'] for row in batch['rejected']] == [2, 3, 4]


def test_pending_to_effective_requires_admin(client, users):
    batch = make_batch(client, users['analyst'], [order('O-1', 'SL-1')])
    assert verify(client, users['viewer'], batch['id']).status_code == 403
    assert verify(client, users['analyst'], batch['id']).status_code == 403
    assert verify(client, users['admin'], batch['id']).status_code == 200


def test_batch_with_only_bad_rows_cannot_become_effective(client, users):
    batch = make_batch(client, users['analyst'], [
        {'order_no': 'O-1', 'member_code': 'SL-1', 'revision': 0,
         'effective_start': '2026-11-09', 'effective_end': '2026-11-30'},
    ])
    assert batch['accepted_rows'] == 0
    r = verify(client, users['admin'], batch['id'])
    assert r.status_code == 422
    detail = client.get(f"/batches/{batch['id']}", headers=users['admin']).json()
    assert detail['state'] == 'pending'


def test_late_lower_revision_does_not_roll_back(client, users):
    add_reader(client, users['analyst'], 'SL-1')
    first = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1', revision=2, end='2026-11-30'),
    ])
    verify(client, users['admin'], first['id'])

    late = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1', revision=1, end='2026-11-10'),
    ])
    body = verify(client, users['admin'], late['id']).json()

    # 快照未变，复用同一版本；迟到旧修订没有回退生效区间
    assert body['entitlement_version'] == 1
    ranges = member_ranges(client, users['analyst'], 'SL-1', version=1)
    assert ranges[0]['end'] == '2026-11-30'
    assert ranges[0]['days'] == 22


def test_newer_revision_arriving_later_still_wins(client, users):
    add_reader(client, users['analyst'], 'SL-1')
    base = make_batch(client, users['analyst'], [order('O-1', 'SL-1', revision=1)])
    verify(client, users['admin'], base['id'])
    late = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1', revision=2, end='2026-12-20'),
    ])
    verify(client, users['admin'], late['id'])
    ranges = member_ranges(client, users['analyst'], 'SL-1', version=2)
    assert ranges[0]['end'] == '2026-12-20'


def test_retry_same_batch_does_not_double_count(client, users):
    rows = [order('O-1', 'SL-1'), order('O-2', 'SL-2')]
    first = make_batch(client, users['analyst'], rows, key='retry-1')
    again = make_batch(client, users['analyst'], rows, key='retry-1')
    assert again['id'] == first['id']
    assert again['accepted_rows'] == first['accepted_rows'] == 2
    assert again['duplicate_rows'] == 0

    # 同一 import_key 直接取回；没有第二个批次、没有重复明细
    listing = client.get('/batches', headers=users['analyst']).json()
    assert len(listing) == 1
    assert len(listing[0]['events']) == 2


def test_retry_never_reaches_second_pending_batch(client, users):
    rows = [order('O-1', 'SL-1')]
    make_batch(client, users['analyst'], rows, key='retry-2')
    listing = client.get('/batches', headers=users['analyst']).json()
    assert len(listing) == 1
    assert listing[0]['accepted_rows'] == 1


def test_resumed_pending_retry_skips_already_recorded_lines(client, users):
    """半途中断后重放：已记账行不重复入账，剩余行补齐，计数与一次性提交一致。"""
    rows = [order('O-1', 'SL-1'), order('O-2', 'SL-2'), order('O-3', 'SL-3')]
    make_batch(client, users['analyst'], rows, key='retry-3')
    with Session() as s:
        from src.models.entities import SubscriptionEvent, SubscriptionBatch
        batch = s.query(SubscriptionBatch).filter_by(import_key='retry-3').one()
        event = s.query(SubscriptionEvent).filter_by(batch_id=batch.id, line_no=3).one()
        s.delete(event)
        batch.accepted_rows = 2
        s.commit()

    resumed = make_batch(client, users['analyst'], rows, key='retry-3')
    assert resumed['accepted_rows'] == 3
    assert resumed['total_rows'] == 3
    assert len(resumed['events']) == 3
    assert [row['line'] for row in resumed['events']] == [1, 2, 3]


def test_same_key_with_different_row_count_is_rejected(client, users):
    make_batch(client, users['analyst'], [order('O-1', 'SL-1')], key='retry-4')
    r = client.post('/batches', json={
        'name': '行数不同',
        'import_key': 'retry-4',
        'rows': [order('O-1', 'SL-1'), order('O-2', 'SL-2')],
    }, headers=users['analyst'])
    assert r.status_code == 409
    assert '同一幂等键只能重放同一份行' in r.json()['detail']


def test_same_key_with_changed_content_is_rejected(client, users):
    make_batch(client, users['analyst'], [order('O-1', 'SL-1', end='2026-11-30')], key='retry-5')
    r = client.post('/batches', json={
        'name': '内容不同',
        'import_key': 'retry-5',
        'rows': [order('O-1', 'SL-1', end='2026-12-31')],
    }, headers=users['analyst'])
    assert r.status_code == 409
    assert '内容不一致' in r.json()['detail']


def test_same_order_revision_content_is_immutable(client, users):
    make_batch(client, users['analyst'], [order('O-1', 'SL-1', end='2026-11-30')])
    conflict = make_batch(client, users['analyst'], [order('O-1', 'SL-1', end='2026-12-31')])
    assert conflict['accepted_rows'] == 0
    assert conflict['rejected_rows'] == 1
    assert '修订不可变' in conflict['rejected'][0]['reason']


def test_duplicate_rows_within_new_batch_are_counted_not_recorded(client, users):
    batch = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1'),
        order('O-1', 'SL-1'),
    ])
    assert batch['accepted_rows'] == 1
    assert batch['duplicate_rows'] == 1
    assert len(batch['events']) == 1


def test_verify_is_idempotent(client, users):
    batch = make_batch(client, users['analyst'], [order('O-1', 'SL-1')])
    first = verify(client, users['admin'], batch['id'])
    assert first.status_code == 200
    again = verify(client, users['admin'], batch['id'])
    assert again.status_code == 409
    versions = client.get('/entitlements', headers=users['analyst']).json()
    assert len(versions) == 1


def test_unchanged_snapshot_reuses_version(client, users):
    batch = make_batch(client, users['analyst'], [order('O-1', 'SL-1', start='2026-11-09', end='2026-11-30')])
    verify(client, users['admin'], batch['id'])
    # 新订单完全落在已有效区间内，合并后快照不变 -> 复用同一版本
    nested = make_batch(client, users['analyst'], [order('O-2', 'SL-1', start='2026-11-12', end='2026-11-20')])
    body = verify(client, users['admin'], nested['id']).json()
    assert body['entitlement_version'] == 1
    assert len(client.get('/entitlements', headers=users['analyst']).json()) == 1


def test_retry_after_effective_does_not_rebook(client, users):
    rows = [order('O-1', 'SL-1')]
    batch = make_batch(client, users['analyst'], rows)
    verify(client, users['admin'], batch['id'])
    # 已生效批次的解析结果与计数保持不变
    before = client.get(f"/batches/{batch['id']}", headers=users['analyst']).json()
    after = client.get(f"/batches/{batch['id']}", headers=users['analyst']).json()
    assert before == after
    assert len(after['events']) == 1


def test_refunded_order_leaves_other_order_active(client, users):
    add_reader(client, users['analyst'], 'SL-1')
    batch = make_batch(client, users['analyst'], [
        order('O-1', 'SL-1', start='2026-11-09', end='2026-11-20', refunded='2026-11-13'),
        order('O-2', 'SL-1', start='2026-11-13', end='2026-11-30'),
    ])
    verify(client, users['admin'], batch['id'])
    ranges = member_ranges(client, users['analyst'], 'SL-1')
    assert ranges == [{
        'start': '2026-11-09', 'end': '2026-11-30', 'days': 22,
        'orders': ['O-1', 'O-2'],
    }]
