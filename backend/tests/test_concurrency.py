"""并发：重试不重复记账、签核竞争、导入与分群/签核各用同一完整版本。"""
import threading

from src.config.database import Session
from src.models.entities import (
    EntitlementSnapshot, EntitlementVersion, Outreach, SubscriptionBatch, SubscriptionEvent,
)
from src.services.batch import verify_batch
from src.services.entitlement import build_snapshot
from tests.conftest import add_reader, order


def run_threads(fn, count):
    results, errors = [], []
    barrier = threading.Barrier(count)

    def worker(index):
        barrier.wait()
        try:
            results.append(fn(index))
        except Exception as exc:  # noqa: BLE001 - 断言时再分类
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def test_concurrent_same_import_key_returns_one_batch(client, users):
    """并发提交同一 import_key：只建一个批次，其余请求取回同一条记录。"""
    rows = [order('O-1', 'SL-1'), order('O-2', 'SL-2')]

    def attempt(_):
        r = client.post('/batches', json={
            'name': '并发导入', 'import_key': 'race-key', 'rows': rows,
        }, headers=users['analyst'])
        return r.status_code, r.json().get('id')

    results, errors = run_threads(attempt, 5)
    assert not errors, errors
    assert {status for status, _ in results} == {200}, results
    assert len({batch_id for _, batch_id in results}) == 1
    with Session() as s:
        assert s.query(SubscriptionBatch).filter_by(import_key='race-key').count() == 1
        assert s.query(SubscriptionEvent).count() == 2


def test_concurrent_verify_creates_one_version(client, users):
    add_reader(client, users['analyst'], 'SL-1')
    batch = client.post('/batches', json={
        'name': '并发核验',
        'rows': [order('O-1', 'SL-1'), order('O-2', 'SL-1', start='2026-12-01', end='2026-12-31')],
    }, headers=users['analyst']).json()

    def attempt(_):
        with Session() as s:
            row = s.get(SubscriptionBatch, batch['id'])
            try:
                verify_batch(s, row, 'admin@demo.local')
                return 'ok'
            except ValueError as exc:
                s.rollback()
                return str(exc)

    results, errors = run_threads(attempt, 4)
    assert not errors, errors
    with Session() as s:
        assert s.query(SubscriptionBatch).filter_by(id=batch['id']).one().state == 'effective'
        assert s.query(EntitlementVersion).count() == 1
        assert s.query(SubscriptionEvent).filter_by(batch_id=batch['id']).count() == 2
        version = s.query(EntitlementVersion).one()
        rows, checksum = build_snapshot(s.query(SubscriptionEvent).all())
        assert version.checksum == checksum
        assert s.query(EntitlementSnapshot).filter_by(version=version.version).count() == len(rows)


def test_concurrent_approve_only_one_wins(client, users):
    for i in range(6):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=4 + i, completion=.2 + i * .08, night=.1 + i * .08)
    batch = client.post('/batches', json={
        'name': '签核竞争基线',
        'rows': [order(f'O-{i}', f'SL-{i}', start='2026-10-01', end='2027-01-31') for i in range(6)],
    }, headers=users['analyst']).json()
    client.post(f"/batches/{batch['id']}/verify", headers=users['admin'])

    from tests.test_qualification import complete_segment, train
    seg = complete_segment(client, users, train(client, users, k=2))
    outreach = client.post('/outreaches', json={
        'segment_id': seg['id'], 'cluster_id': 0,
        'title': '并发签核', 'note': '并发签核只允许一个请求成功并冻结名单',
        'send_date': '2026-11-15',
    }, headers=users['analyst']).json()

    def attempt(_):
        r = client.post(f"/outreaches/{outreach['id']}/approve", headers=users['admin'])
        return r.status_code

    results, errors = run_threads(attempt, 4)
    assert not errors, errors
    assert sorted(results).count(200) == 1, results
    assert all(code in (200, 409) for code in results), results
    with Session() as s:
        row = s.get(Outreach, outreach['id'])
        assert row.status == 'approved'
        assert row.approved_at
        assert row.members == outreach['members']


def test_import_and_segment_use_complete_versions(client, users):
    """导入生效与分群并发：每个分群绑定一个完整、自洽的权益版本。"""
    warmup = client.post('/batches', json={
        'name': '基线',
        'rows': [order(f'O-{i}', f'SL-{i}', start='2026-10-01', end='2027-01-31') for i in range(8)],
    }, headers=users['analyst']).json()
    client.post(f"/batches/{warmup['id']}/verify", headers=users['admin'])
    for i in range(8):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=4 + i, completion=.2 + i * .08, night=.1 + i * .08)

    imports = []
    for revision in (2, 3):
        imports.append(client.post('/batches', json={
            'name': f'并发导入 {revision}',
            'rows': [order('O-0', 'SL-0', revision=revision, start='2026-10-01', end='2027-01-31', refunded='2026-11-20')],
        }, headers=users['analyst']).json())

    def do_import(index):
        batch_id = imports[index % len(imports)]['id']
        with Session() as s:
            row = s.get(SubscriptionBatch, batch_id)
            try:
                verify_batch(s, row, 'admin@demo.local')
                return 'effective'
            except ValueError:
                s.rollback()
                return 'skipped'

    def do_segment(_):
        r = client.post('/segments', json={
            'name': '并发分群', 'k': 2,
            'features': ['weekly_reading', 'completion'],
            'week_start': '2026-11-09',
        }, headers=users['analyst'])
        return r.status_code

    results, errors = run_threads(lambda i: (do_import(i) if i % 2 else do_segment(i)), 6)
    assert not errors, errors
    assert 200 in results

    with Session() as s:
        versions = s.query(EntitlementVersion).order_by(EntitlementVersion.version).all()
        assert len({v.version for v in versions}) == len(versions)
        assert [v.version for v in versions] == list(range(1, len(versions) + 1))
        for version in versions:
            rows = s.query(EntitlementSnapshot).filter_by(version=version.version).all()
            assert version.ranges == len(rows)
            assert version.members == len({row.member_code for row in rows})
            # 每个版本内部区间已合并：同一会员的区间互不重叠
            by_member = {}
            for row in rows:
                by_member.setdefault(row.member_code, []).append((row.start_date, row.end_date))
            for spans in by_member.values():
                spans.sort()
                for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
                    assert next_start > prev_end

    segments = client.get('/segments', headers=users['analyst']).json()
    assert segments
    for segment in segments:
        assert segment['entitlement_version'] in {v.version for v in versions}
        assert segment['qualification']['entitlement_version'] == segment['entitlement_version']
        basis = segment['qualification']
        assert basis['counts']['included'] == len(basis['included'])
        assert basis['counts']['excluded'] == len(basis['excluded'])
