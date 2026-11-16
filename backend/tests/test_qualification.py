"""分群取样与触达重算：周界、退款、迟到修订、签核竞争。"""
from tests.conftest import add_reader, order

WEEK = '2026-11-09'


def make_batch(client, headers, rows):
    r = client.post('/batches', json={'name': 'b', 'rows': rows}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def verify(client, headers, batch_id):
    r = client.post(f'/batches/{batch_id}/verify', headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def seed_version(client, users, rows):
    batch = make_batch(client, users['analyst'], rows)
    return verify(client, users['admin'], batch['id'])['entitlement_version']


def train(client, users, **extra):
    payload = {'name': '测试分群', 'k': 2,
               'features': ['weekly_reading', 'completion', 'night_share'],
               'week_start': WEEK}
    payload.update(extra)
    r = client.post('/segments', json=payload, headers=users['analyst'])
    assert r.status_code == 200, r.text
    return r.json()


def test_segment_samples_only_full_week_members(client, users):
    for i in range(6):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=5 + i, completion=.2 + i * .1, night=.1 + i * .1)
    seed_version(client, users, [
        # 整周覆盖 -> 纳入
        order('O-0', 'SL-0', start='2026-11-01', end='2026-12-01'),
        # 周一开始 -> 纳入
        order('O-1', 'SL-1', start='2026-11-09', end='2026-11-15'),
        # 周日结束但仍覆盖整周 -> 纳入
        order('O-2', 'SL-2', start='2026-11-09', end='2026-11-15'),
        # 周六结束 -> 缺周日，排除
        order('O-3', 'SL-3', start='2026-11-09', end='2026-11-14'),
        # 周三开始 -> 排除
        order('O-4', 'SL-4', start='2026-11-11', end='2026-11-30'),
        # 周二退款 -> 排除
        order('O-5', 'SL-5', start='2026-11-01', end='2026-12-01', refunded='2026-11-10'),
    ])
    seg = train(client, users)
    basis = client.get(f"/segments/{seg['id']}/qualification", headers=users['analyst']).json()
    included = {row['code'] for row in basis['included']}
    excluded = {row['code']: row for row in basis['excluded']}
    assert included == {'SL-0', 'SL-1', 'SL-2'}
    assert set(excluded) == {'SL-3', 'SL-4', 'SL-5'}
    assert '仅覆盖6/7天' in excluded['SL-3']['reason']
    assert excluded['SL-3']['covered_days'] == 6
    assert excluded['SL-4']['covered_days'] == 5
    assert excluded['SL-5']['covered_days'] == 1


def test_week_start_normalizes_to_monday(client, users):
    for i in range(4):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=5 + i, completion=.2 + i * .1, night=.1 + i * .1)
    seed_version(client, users, [order(f'O-{i}', f'SL-{i}', start='2026-11-09', end='2026-11-15') for i in range(4)])
    seg = train(client, users, week_start='2026-11-12')
    assert seg['week_start'] == '2026-11-09'
    assert seg['week_end'] == '2026-11-15'


def complete_segment(client, users, segment):
    """直接跑完聚类，避免依赖 Redis worker。"""
    from src.config.database import Session
    from src.models.entities import Segment
    from src.services.analysis import cluster
    with Session() as s:
        row = s.get(Segment, segment['id'])
        row.result = {**cluster(row.result['snapshot'], row.features, row.k), 'snapshot': row.result['snapshot']}
        row.state = 'done'
        s.commit()
    return client.get(f"/segments/{segment['id']}", headers=users['analyst']).json()


def test_segment_freezes_entitlement_version(client, users):
    for i in range(4):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=5 + i, completion=.2 + i * .1, night=.1 + i * .1)
    v1 = seed_version(client, users, [order(f'O-{i}', f'SL-{i}', start='2026-11-01', end='2026-12-01') for i in range(4)])

    raw = train(client, users)
    assert raw['entitlement_version'] == v1
    seg = complete_segment(client, users, raw)

    # 新版本把 SL-0 的同一订单退款，分群不随之漂移
    v2 = seed_version(client, users, [order('O-0', 'SL-0', revision=2, start='2026-11-01', end='2026-12-01', refunded='2026-11-05')])
    assert v2 == v1 + 1
    detail = client.get(f"/segments/{seg['id']}", headers=users['analyst']).json()
    assert detail['entitlement_version'] == v1
    assert detail['result']['n'] == 4
    codes = {m['code'] for m in detail['result']['members']}
    assert 'SL-0' in codes
    # 新版本下 SL-0 已不满足整周有权益
    basis = client.get(f"/segments/{seg['id']}/qualification", headers=users['analyst']).json()
    assert basis['entitlement_version'] == v1
    assert 'SL-0' in {row['code'] for row in basis['included']}


def test_segment_rejects_explicit_missing_version(client, users):
    for i in range(4):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=5 + i, completion=.2 + i * .1, night=.1 + i * .1)
    seed_version(client, users, [order(f'O-{i}', f'SL-{i}', start='2026-11-01', end='2026-12-01') for i in range(4)])
    r = client.post('/segments', json={
        'name': '缺失版本', 'k': 2, 'features': ['weekly_reading', 'completion'],
        'week_start': WEEK, 'entitlement_version': 99,
    }, headers=users['analyst'])
    assert r.status_code == 409


def test_segment_fails_when_too_few_entitled(client, users):
    for i in range(3):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=5 + i, completion=.2 + i * .1, night=.1 + i * .1)
    seed_version(client, users, [order(f'O-{i}', f'SL-{i}', start='2026-11-01', end='2026-12-01') for i in range(2)])
    r = client.post('/segments', json={
        'name': '样本不足', 'k': 2, 'features': ['weekly_reading', 'completion'],
        'week_start': WEEK,
    }, headers=users['analyst'])
    assert r.status_code == 422
    assert '整周有权益' in r.json()['detail']


def ready_segment(client, users, n=8):
    for i in range(n):
        add_reader(client, users['analyst'], f'SL-{i}', weekly=4 + i, completion=.2 + i * .08, night=.1 + i * .08)
    seed_version(client, users, [
        order(f'O-{i}', f'SL-{i}', start='2026-10-01', end='2027-01-31') for i in range(n)
    ])
    return complete_segment(client, users, train(client, users, k=2))


def cluster_members(segment, cluster_id):
    return {m['code'] for m in segment['result']['members'] if m['cluster_id'] == cluster_id}


def test_outreach_recomputes_on_send_date(client, users):
    seg = ready_segment(client, users)
    cluster_id = 0
    codes = sorted(cluster_members(seg, cluster_id))
    victim = codes[0]
    victim_index = int(victim.split('-')[1])

    # 发送日前一天退款该成员的唯一订单：分群时仍在册，发送日已不可达
    seed_version(client, users, [
        order(f'O-{victim_index}', victim, revision=2,
              start='2026-10-01', end='2027-01-31', refunded='2026-11-24'),
    ])
    r = client.post('/outreaches', json={
        'segment_id': seg['id'], 'cluster_id': cluster_id,
        'title': '发送日重算', 'note': '测试发送日可达名单重算逻辑',
        'send_date': '2026-11-25',
    }, headers=users['analyst'])
    assert r.status_code == 200, r.text
    body = r.json()
    assert victim not in body['members']
    excluded = {row['code']: row for row in body['entitlement_basis']['excluded']}
    assert victim in excluded
    assert '发送日不在任何有效订阅区间内' in excluded[victim]['reason']
    assert excluded[victim]['last_covered_end'] == '2026-11-23'
    assert body['entitlement_version'] == 2


def test_approved_outreach_is_frozen(client, users):
    seg = ready_segment(client, users)
    cluster_id = 0
    r = client.post('/outreaches', json={
        'segment_id': seg['id'], 'cluster_id': cluster_id,
        'title': '冻结名单', 'note': '签核后名单不可被新订单重算',
        'send_date': '2026-11-15',
    }, headers=users['analyst'])
    outreach = r.json()
    frozen = list(outreach['members'])
    approved = client.post(f"/outreaches/{outreach['id']}/approve", headers=users['admin'])
    assert approved.status_code == 200
    assert approved.json()['members'] == frozen

    # 之后新版本让群成员全部退款，旧方案仍然保持冻结名单
    codes = sorted(cluster_members(seg, cluster_id))
    seed_version(client, users, [
        order(f'O-{int(code.split("-")[1])}', code, revision=2,
              start='2026-10-01', end='2027-01-31', refunded='2026-11-01')
        for code in codes
    ])

    detail = client.get('/outreaches', headers=users['analyst']).json()[0]
    assert detail['members'] == frozen
    assert detail['status'] == 'approved'
    assert client.post(f"/outreaches/{outreach['id']}/refresh", headers=users['analyst']).status_code == 409
    assert client.post(f"/outreaches/{outreach['id']}/approve", headers=users['admin']).status_code == 409


def test_approval_race_freezes_once(client, users):
    seg = ready_segment(client, users)
    outreach = client.post('/outreaches', json={
        'segment_id': seg['id'], 'cluster_id': 0,
        'title': '签核竞争', 'note': '两个请求同时签核只允许一次成功',
        'send_date': '2026-11-15',
    }, headers=users['analyst']).json()
    first = client.post(f"/outreaches/{outreach['id']}/approve", headers=users['admin'])
    second = client.post(f"/outreaches/{outreach['id']}/approve", headers=users['admin'])
    assert first.status_code == 200
    assert second.status_code == 409
    detail = client.get('/outreaches', headers=users['analyst']).json()[0]
    assert detail['approved_at']


def test_outreach_draft_uses_latest_full_version(client, users):
    seg = ready_segment(client, users)
    outreach = client.post('/outreaches', json={
        'segment_id': seg['id'], 'cluster_id': 0,
        'title': '重算草案', 'note': '草案按最新完整权益版本重算可达名单',
        'send_date': '2026-11-15',
    }, headers=users['analyst']).json()
    before = outreach['entitlement_version']
    seed_version(client, users, [
        order('O-1', 'SL-1', revision=2, start='2026-10-01', end='2027-01-31', refunded='2026-11-14'),
    ])
    refreshed = client.post(f"/outreaches/{outreach['id']}/refresh", headers=users['analyst']).json()
    assert refreshed['entitlement_version'] == before + 1
    assert refreshed['status'] == 'draft'
