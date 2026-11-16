import os
import tempfile
from pathlib import Path

# 默认测 SQLite；设置 TEST_DATABASE_URL 时改测真实 PostgreSQL。
_PG = os.environ.get('TEST_DATABASE_URL')
if _PG:
    os.environ['DATABASE_URL'] = _PG
else:
    _DB_DIR = tempfile.mkdtemp(prefix='reader-tests-')
    os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_DB_DIR) / 'test.db')
os.environ.setdefault('JWT_SECRET', 'test-secret')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/15')

import pytest

from src.config.database import Base, Session, engine
from src.models.entities import User
from src.utils.security import hash_password


class FakeRedis:
    def __init__(self):
        self.items = []

    def rpush(self, key, value):
        self.items.append((key, value))
        return len(self.items)


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    fake = FakeRedis()

    import src.routes.api as api
    monkeypatch.setattr(api.redis, 'Redis', type('R', (), {'from_url': staticmethod(lambda *a, **k: fake)}))
    with Session() as s:
        for role in ('admin', 'analyst', 'viewer'):
            s.add(User(email=role + '@demo.local', role=role, password=hash_password('Demo123!')))
        s.commit()
    yield fake
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import src.main as main
    with TestClient(main.app) as c:
        yield c


def auth(client, role='analyst'):
    r = client.post('/auth/login', json={'email': role + '@demo.local', 'password': 'Demo123!'})
    assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['token']}


@pytest.fixture
def users(client):
    return {role: auth(client, role) for role in ('admin', 'analyst', 'viewer')}


def add_reader(client, headers, code, weekly=10, completion=.5, night=.3):
    r = client.post('/readers', json={
        'code': code, 'weekly_reading': weekly, 'completion': completion,
        'night_share': night, 'note': 'test',
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def order(order_no, member, revision=1, start='2026-11-09', end='2026-11-30', refunded=None):
    return {
        'order_no': order_no, 'member_code': member, 'revision': revision,
        'effective_start': start, 'effective_end': end, 'refunded_on': refunded,
    }
